import gzip
import json
import logging
from concurrent import futures
from typing import Any, Dict, List

import grpc
from django.core.management.base import BaseCommand
from google.protobuf.internal.decoder import _DecodeVarint32
from google.protobuf.message import DecodeError
from pygnmi.client import telemetryParser
from pygnmi.spec.v080 import gnmi_pb2

from devices.models import Device
from monitoring.gnmi_parser import format_metrics_from_map, parse_gnmi_notification
from monitoring.services import MonitoringService

logger = logging.getLogger('monitoring.dialout')

_H3C_LAYOUT_LOGGED = False
_H3C_PAYLOAD_PREVIEW_LOGGED = False
_H3C_NO_INTERFACE_LOGGED = False

_OSPF_STATE_MAP = {
    1: 'Down',
    2: 'Attempt',
    3: 'Init',
    4: 'TwoWay',
    5: 'ExStart',
    6: 'Exchange',
    7: 'Loading',
    8: 'Full',
}

_H3C_OSPF_ZERO_BASE_STATE_MAP = {
    0: 'Down',
    1: 'Attempt',
    2: 'Init',
    3: 'TwoWay',
    4: 'ExStart',
    5: 'Exchange',
    6: 'Loading',
    7: 'Full',
}


def _decode_h3c_ospf_state(raw_state):
    # Normalize H3C OSPF state to standard 1-based values used by UI
    if raw_state is None:
        return None, 'Unknown', False

    # H3C dial-out payloads use zero-based OSPF states (0..7).
    if raw_state in _H3C_OSPF_ZERO_BASE_STATE_MAP:
        state_name = _H3C_OSPF_ZERO_BASE_STATE_MAP[raw_state]
        normalized_state = raw_state + 1
        return normalized_state, state_name, state_name.lower() == 'full'

    # Keep compatibility if a one-based value is ever received.
    state_name = _OSPF_STATE_MAP.get(raw_state, f'Unknown({raw_state})')
    return raw_state, state_name, state_name.lower() == 'full'


def _parse_subscribe_response(payload):
    if not payload:
        return None

    try:
        message = gnmi_pb2.SubscribeResponse()
        message.ParseFromString(payload)
        if message.HasField('update') or message.HasField('sync_response'):
            return message
    except DecodeError:
        return None
    except Exception:
        return None

    return None


def _iter_wire_fields(payload):
    pos = 0
    total = len(payload)

    while pos < total:
        try:
            tag, pos = _DecodeVarint32(payload, pos)
        except Exception:
            return

        field_num = tag >> 3
        wire_type = tag & 0x7

        if wire_type == 0:  # varint
            try:
                value, pos = _DecodeVarint32(payload, pos)
            except Exception:
                return
            yield field_num, wire_type, value
            continue

        if wire_type == 1:  # fixed64
            end = pos + 8
            if end > total:
                return
            yield field_num, wire_type, payload[pos:end]
            pos = end
            continue

        if wire_type == 2:  # length-delimited
            try:
                length, pos = _DecodeVarint32(payload, pos)
            except Exception:
                return

            end = pos + length
            if end > total:
                return

            yield field_num, wire_type, payload[pos:end]
            pos = end
            continue

        if wire_type == 5:  # fixed32
            end = pos + 4
            if end > total:
                return
            yield field_num, wire_type, payload[pos:end]
            pos = end
            continue

        return


def _decode_utf8(value):
    try:
        return value.decode('utf-8')
    except UnicodeDecodeError:
        return None


def _try_parse_json_bytes(value):
    text = _decode_utf8(value)
    if not text:
        return None

    stripped = text.lstrip()
    if not stripped or stripped[0] not in '{[':
        return None

    try:
        return json.loads(text)
    except json.JSONDecodeError:
        return None


def _find_json_in_envelope(payload, depth=0, max_depth=6):
    if not payload or depth > max_depth:
        return None

    parsed = _try_parse_json_bytes(payload)
    if parsed is not None:
        return parsed

    for _, wire_type, value in _iter_wire_fields(payload):
        if wire_type != 2 or not isinstance(value, bytes):
            continue

        parsed = _try_parse_json_bytes(value)
        if parsed is not None:
            return parsed

        nested = _find_json_in_envelope(value, depth + 1, max_depth)
        if nested is not None:
            return nested

    return None


def _build_interface_path(sensor_path, interface_name):
    if not sensor_path:
        return f'interfaces/interface[name={interface_name}]'

    if 'interface[name=' in sensor_path:
        return sensor_path

    if 'interface/' in sensor_path:
        return sensor_path.replace('interface/', f'interface[name={interface_name}]/', 1)

    if sensor_path.endswith('/interface'):
        return f'{sensor_path}[name={interface_name}]'

    if '/interface' in sensor_path:
        return sensor_path.replace('/interface', f'/interface[name={interface_name}]', 1)

    return f'{sensor_path}/interface[name={interface_name}]'


def _extract_interface_updates(sensor_path, json_payload):
    if not isinstance(json_payload, dict):
        return []

    interfaces = json_payload.get('interfaces')
    if not isinstance(interfaces, dict):
        return []

    interface_data = interfaces.get('interface')
    if interface_data is None:
        return []

    if isinstance(interface_data, list):
        entries = interface_data
    elif isinstance(interface_data, dict):
        if 'name' in interface_data or 'state' in interface_data:
            entries = [interface_data]
        else:
            entries = []
            for key, value in interface_data.items():
                if not isinstance(value, dict):
                    continue
                merged = dict(value)
                merged.setdefault('name', key)
                entries.append(merged)
    else:
        return []

    updates = []
    for entry in entries:
        if not isinstance(entry, dict):
            continue

        interface_name = entry.get('name')
        state_obj = entry.get('state')
        if not interface_name and isinstance(state_obj, dict):
            interface_name = state_obj.get('name')

        if not interface_name:
            continue

        metric_value = entry
        if isinstance(state_obj, dict) and isinstance(state_obj.get('counters'), dict):
            metric_value = state_obj['counters']

        updates.append(
            {
                'path': _build_interface_path(sensor_path, interface_name),
                'val': metric_value,
            }
        )

    return updates


def _preview_update_paths(notification, limit=3):
    if not isinstance(notification, dict):
        return []

    updates = notification.get('update')
    if not isinstance(updates, list):
        return []

    paths = []
    for item in updates:
        if not isinstance(item, dict):
            continue
        path = item.get('path')
        if path is not None:
            paths.append(str(path))
        if len(paths) >= limit:
            break

    return paths


def _unwrap_h3c_notification_payload(json_payload):
    if not isinstance(json_payload, dict):
        return json_payload

    notification = json_payload.get('Notification')
    if notification is None:
        return json_payload

    if isinstance(notification, dict):
        return notification

    if isinstance(notification, list):
        for item in notification:
            if isinstance(item, dict) and ('interfaces' in item or 'update' in item):
                return item

        for item in notification:
            if isinstance(item, dict):
                return item

    return json_payload


def _to_float(value):
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _to_int(value):
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _to_status(value):
    if value is None:
        return None

    text = str(value).strip().lower()
    if text in {'up', '1', 'true'}:
        return 1
    if text in {'down', '2', 'false'}:
        return 2

    return _to_int(value)


def _iter_list_like(value):
    if isinstance(value, list):
        return value
    if isinstance(value, dict):
        return [value]
    return []


def _empty_metrics() -> Dict[str, Any]:
    return {
        'traffic': [],
        'packet_loss': None,
        'connections': None,
        'interfaces': [],
        'ospf_neighbors': [],
        'cpu_usage': None,
        'memory_usage': None,
    }


def _merge_interface_list(base: List[Dict[str, Any]], incoming: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    merged_map: Dict[str, Dict[str, Any]] = {}

    for interface in base:
        if not isinstance(interface, dict):
            continue
        name = interface.get('name')
        if not name:
            continue
        merged_map[name] = dict(interface)

    for interface in incoming:
        if not isinstance(interface, dict):
            continue
        name = interface.get('name')
        if not name:
            continue

        current = merged_map.get(name, {})
        current.update(interface)
        merged_map[name] = current

    return list(merged_map.values())


def _merge_metrics(base: Dict[str, Any], incoming: Dict[str, Any]) -> Dict[str, Any]:
    if not isinstance(incoming, dict):
        return base

    base['interfaces'] = _merge_interface_list(
        base.get('interfaces', []),
        incoming.get('interfaces', []),
    )

    if incoming.get('traffic'):
        base['traffic'] = incoming.get('traffic')

    if incoming.get('ospf_neighbors'):
        base['ospf_neighbors'] = incoming.get('ospf_neighbors')

    for scalar_key in ('packet_loss', 'connections', 'cpu_usage', 'memory_usage'):
        value = incoming.get(scalar_key)
        if value is not None:
            base[scalar_key] = value

    return base


def _extract_h3c_ifmgr_statistics_metrics(payload) -> Dict[str, Any]:
    metrics = _empty_metrics()
    if not isinstance(payload, dict):
        return metrics

    interfaces_root = (
        payload.get('Ifmgr', {})
        .get('Statistics', {})
        .get('Interface')
    )

    for interface in _iter_list_like(interfaces_root):
        if not isinstance(interface, dict):
            continue

        name = interface.get('Name') or interface.get('name')
        if not name:
            continue

        in_octets = _to_int(interface.get('InOctets'))
        out_octets = _to_int(interface.get('OutOctets'))
        in_rate = _to_float(interface.get('InRate'))
        out_rate = _to_float(interface.get('OutRate'))
        in_discards = _to_int(interface.get('InDiscards'))
        out_discards = _to_int(interface.get('OutDiscards'))

        iface_metrics = {
            'name': name,
            'if_index': _to_int(interface.get('IfIndex')),
        }
        if in_octets is not None:
            iface_metrics['in_octets'] = in_octets
        if out_octets is not None:
            iface_metrics['out_octets'] = out_octets
        if in_rate is not None:
            iface_metrics['in_mbps'] = round(in_rate / 1000.0, 3)
        if out_rate is not None:
            iface_metrics['out_mbps'] = round(out_rate / 1000.0, 3)
        if in_discards is not None:
            iface_metrics['in_drop_rate'] = in_discards
        if out_discards is not None:
            iface_metrics['out_drop_rate'] = out_discards

        metrics['interfaces'].append(iface_metrics)
        metrics['traffic'].append(
            {
                'interface': name,
                'in_octets': in_octets or 0,
                'out_octets': out_octets or 0,
                'is_first_collection': False,
            }
        )

    return metrics


def _extract_h3c_interface_state_metrics(payload) -> Dict[str, Any]:
    metrics = _empty_metrics()
    if not isinstance(payload, dict):
        return metrics

    interfaces_root = (
        payload.get('interfaces', {})
        .get('interface')
    )

    for interface in _iter_list_like(interfaces_root):
        if not isinstance(interface, dict):
            continue

        state = interface.get('state', {}) if isinstance(interface.get('state'), dict) else {}
        name = interface.get('name') or state.get('name')
        if not name:
            continue

        status = _to_status(state.get('oper-status'))
        if status is None:
            status = _to_status(state.get('admin-status'))

        iface_metrics = {'name': name}
        if status is not None:
            iface_metrics['status'] = status

        metrics['interfaces'].append(iface_metrics)

    return metrics


def _extract_h3c_ospf_metrics(payload) -> Dict[str, Any]:
    metrics = _empty_metrics()
    if not isinstance(payload, dict):
        return metrics

    neighbors_root = (
        payload.get('OSPF', {})
        .get('Neighbours', {})
        .get('Nbr')
    )

    for neighbor in _iter_list_like(neighbors_root):
        if not isinstance(neighbor, dict):
            continue

        raw_state = _to_int(neighbor.get('State'))
        state, state_name, is_full = _decode_h3c_ospf_state(raw_state)
        metrics['ospf_neighbors'].append(
            {
                'neighbor_ip': neighbor.get('NbrAddress'),
                'router_id': neighbor.get('NbrRouterId'),
                'state': state,
                'state_name': state_name,
                'is_full': is_full,
                'interface_index': _to_int(neighbor.get('IfIndex')),
                'raw_state': raw_state,
            }
        )

    return metrics


def _extract_h3c_cpu_metrics(payload) -> Dict[str, Any]:
    metrics = _empty_metrics()
    if not isinstance(payload, dict):
        return metrics

    cpu_root = (
        payload.get('Device', {})
        .get('CPUs', {})
        .get('CPU')
    )

    cpu_values = []
    for cpu in _iter_list_like(cpu_root):
        if not isinstance(cpu, dict):
            continue
        usage = _to_float(cpu.get('CPUUsage'))
        if usage is not None:
            cpu_values.append(usage)

    if cpu_values:
        metrics['cpu_usage'] = round(sum(cpu_values) / len(cpu_values), 2)

    return metrics


def _extract_h3c_memory_metrics(payload) -> Dict[str, Any]:
    metrics = _empty_metrics()
    if not isinstance(payload, dict):
        return metrics

    memory_root = (
        payload.get('Diagnostic', {})
        .get('Memories', {})
        .get('Memory')
    )

    memory_values = []
    for memory in _iter_list_like(memory_root):
        if not isinstance(memory, dict):
            continue

        total = _to_float(memory.get('Total'))
        used = _to_float(memory.get('Used'))
        usage = None

        if total and total > 0 and used is not None:
            usage = (used / total) * 100.0
        else:
            free_ratio = memory.get('FreeRatio')
            if isinstance(free_ratio, str) and free_ratio.endswith('%'):
                free = _to_float(free_ratio[:-1])
                if free is not None:
                    usage = 100.0 - free

        if usage is not None:
            memory_values.append(usage)

    if memory_values:
        metrics['memory_usage'] = round(sum(memory_values) / len(memory_values), 2)

    return metrics


def _extract_h3c_metrics(sensor_path, json_payload) -> Dict[str, Any]:
    metrics = _empty_metrics()
    payload = _unwrap_h3c_notification_payload(json_payload)

    # 对 H3C 一次推送里的不同 sensor path 做统一提取，避免遗漏核心监控维度。
    _merge_metrics(metrics, _extract_h3c_interface_state_metrics(payload))
    _merge_metrics(metrics, _extract_h3c_ifmgr_statistics_metrics(payload))
    _merge_metrics(metrics, _extract_h3c_ospf_metrics(payload))
    _merge_metrics(metrics, _extract_h3c_cpu_metrics(payload))
    _merge_metrics(metrics, _extract_h3c_memory_metrics(payload))

    if sensor_path and sensor_path.lower() not in {
        'ifmgr/statistics',
        'interfaces/interface/state',
        'ospf/neighbours',
        'ospf/neighbors',
        'device/cpus',
        'diagnostic/memories',
    }:
        logger.debug('Unmapped H3C sensor_path=%s, fallback extraction applied.', sensor_path)

    return metrics


def _metrics_has_observable_data(metrics: Dict[str, Any]) -> bool:
    return any(
        [
            metrics.get('traffic'),
            metrics.get('interfaces'),
            metrics.get('ospf_neighbors'),
            metrics.get('packet_loss') is not None,
            metrics.get('connections') is not None,
            metrics.get('cpu_usage') is not None,
            metrics.get('memory_usage') is not None,
        ]
    )


def _make_gnmi_like_update(sensor_path, json_payload):
    json_payload = _unwrap_h3c_notification_payload(json_payload)

    if isinstance(json_payload, dict):
        if 'update' in json_payload and isinstance(json_payload['update'], dict):
            inner = json_payload['update']
            if isinstance(inner.get('update'), list):
                return {'update': inner}

        if isinstance(json_payload.get('update'), list):
            return {'update': {'update': json_payload['update']}}

        interface_updates = _extract_interface_updates(sensor_path, json_payload)
        if interface_updates:
            return {'update': {'update': interface_updates}}

    path = sensor_path or ''
    return {'update': {'update': [{'path': path, 'val': json_payload}]}}


def _decode_h3c_dialout_msg(payload):
    global _H3C_LAYOUT_LOGGED
    global _H3C_PAYLOAD_PREVIEW_LOGGED

    sensor_path = None
    json_payload = None
    device_info = {}

    for field_num, wire_type, value in _iter_wire_fields(payload):
        if wire_type != 2 or not isinstance(value, bytes):
            continue

        if field_num == 1:
            # DeviceInfo-like nested message, we keep it for diagnostics.
            for sub_num, sub_wire_type, sub_val in _iter_wire_fields(value):
                if sub_wire_type != 2 or not isinstance(sub_val, bytes):
                    continue
                sub_text = _decode_utf8(sub_val)
                if sub_text:
                    device_info[sub_num] = sub_text

        elif field_num == 2:
            path_text = _decode_utf8(value)
            if path_text:
                sensor_path = path_text

        elif field_num == 3:
            parsed = _try_parse_json_bytes(value)
            if parsed is not None:
                json_payload = parsed

    if json_payload is None:
        json_payload = _find_json_in_envelope(payload)

    if json_payload is None:
        return None

    if isinstance(json_payload, dict) and not _H3C_PAYLOAD_PREVIEW_LOGGED:
        _H3C_PAYLOAD_PREVIEW_LOGGED = True
        logger.info(
            'H3C jsonData preview: sensor_path=%s top_keys=%s',
            sensor_path,
            sorted(list(json_payload.keys()))[:12],
        )

    if device_info and not _H3C_LAYOUT_LOGGED:
        _H3C_LAYOUT_LOGGED = True
        logger.info(
            'Detected H3C DialoutMsg layout: vendor=%s device=%s model=%s mode=%s sample=%s',
            device_info.get(1),
            device_info.get(2),
            device_info.get(3),
            device_info.get(4),
            device_info.get(5),
        )

    resp = _make_gnmi_like_update(sensor_path, json_payload)
    resp['_h3c_sensor_path'] = sensor_path
    resp['_h3c_metrics'] = _extract_h3c_metrics(sensor_path, json_payload)
    return resp


def _iter_length_delimited_fields(payload):
    for _, wire_type, value in _iter_wire_fields(payload):
        if wire_type == 2 and isinstance(value, bytes):
            yield value


def _extract_subscribe_from_envelope(payload, depth=0, max_depth=7):
    if not payload or depth > max_depth:
        return None

    direct = _parse_subscribe_response(payload)
    if direct is not None:
        return direct

    # Some devices may compress message payloads before wrapping.
    if len(payload) > 2 and payload[0] == 0x1F and payload[1] == 0x8B:
        try:
            uncompressed = gzip.decompress(payload)
            parsed = _extract_subscribe_from_envelope(uncompressed, depth + 1, max_depth)
            if parsed is not None:
                return parsed
        except OSError:
            pass

    for nested in _iter_length_delimited_fields(payload):
        if len(nested) < 2:
            continue

        parsed = _extract_subscribe_from_envelope(nested, depth + 1, max_depth)
        if parsed is not None:
            return parsed

    return None

class GenericReceiver(grpc.GenericRpcHandler):
    def __init__(self):
        self.monitoring_service = MonitoringService()

    def _get_peer_ip(self, context):
        peer = context.peer()
        # peer format is usually "ipv4:192.168.50.100:12345"
        if peer and ':' in peer:
            parts = peer.split(':')
            if len(parts) >= 2:
                # Returns 192.168.50.100
                return parts[1]
        return peer

    def service(self, handler_call_details):
        logger.info(f"Received gRPC call on method: {handler_call_details.method}")

        # Return a custom RpcMethodHandler
        def stream_stream_handler(request_iterator, context):
            peer_ip = self._get_peer_ip(context)
            logger.info(f"Stream from peer IP: {peer_ip}")
            
            # Find the device
            device = Device.objects.filter(ip_address=peer_ip, telemetry_mode='dial_out').first()
            if not device:
                logger.warning(f"Unknown device IP or dial_out disabled: {peer_ip}")
            else:
                logger.info(f"Matched device: {device.name}")

            for raw_chunk in request_iterator:
                try:
                    resp_dict = None

                    if isinstance(raw_chunk, bytes):
                        payload = raw_chunk
                    elif isinstance(raw_chunk, str):
                        payload = raw_chunk.encode('utf-8', errors='ignore')
                    else:
                        payload = bytes(raw_chunk)

                    parsed_msg = _extract_subscribe_from_envelope(payload)
                    if parsed_msg is not None:
                        resp_dict = telemetryParser(parsed_msg)
                    else:
                        if handler_call_details.method == '/grpc_dialout.GRPCDialout/Dialout':
                            resp_dict = _decode_h3c_dialout_msg(payload)

                        if resp_dict is None:
                            logger.debug(
                                "Unable to decode SubscribeResponse from %s payload (size=%s, head=%r)",
                                handler_call_details.method,
                                len(payload),
                                payload[:64],
                            )

                            # Keep JSON fallback for devices that send plain-text payload.
                            try:
                                if payload.lstrip().startswith((b'{', b'[')):
                                    resp_dict = json.loads(payload.decode('utf-8'))
                            except Exception as json_err:
                                logger.debug(f"JSON fallback decode failed: {json_err}")
                                continue

                    # Process the parsed metrics dictionary
                    if resp_dict and isinstance(resp_dict, dict) and device:
                        metrics = _empty_metrics()

                        h3c_metrics = resp_dict.get('_h3c_metrics')
                        if isinstance(h3c_metrics, dict):
                            _merge_metrics(metrics, h3c_metrics)

                        notification = resp_dict.get('update')
                        if isinstance(notification, dict):
                            global _H3C_NO_INTERFACE_LOGGED
                            interface_map = {}
                            parse_gnmi_notification(notification, interface_map)
                            parsed_metrics = format_metrics_from_map(interface_map)
                            _merge_metrics(metrics, parsed_metrics)

                            if not interface_map and not metrics.get('interfaces'):
                                if not _H3C_NO_INTERFACE_LOGGED:
                                    _H3C_NO_INTERFACE_LOGGED = True
                                    logger.info(
                                        'Decoded telemetry but no interface fields matched parser for %s (sample_paths=%s)',
                                        device.name,
                                        _preview_update_paths(notification),
                                    )
                                logger.debug(
                                    'Decoded update but no interfaces extracted for %s (paths=%s)',
                                    device.name,
                                    _preview_update_paths(notification),
                                )

                        if _metrics_has_observable_data(metrics):
                            logger.info(
                                'Extracted metrics for %s: interfaces=%s traffic=%s ospf=%s cpu=%s memory=%s',
                                device.name,
                                len(metrics.get('interfaces', [])),
                                len(metrics.get('traffic', [])),
                                len(metrics.get('ospf_neighbors', [])),
                                metrics.get('cpu_usage'),
                                metrics.get('memory_usage'),
                            )
                            metrics['_partial_update'] = True
                            stored_count = self.monitoring_service.store_metrics(device, metrics)
                            logger.debug(f"Stored {stored_count} metrics.")
                except Exception as e:
                    logger.error(f"Failed to process chunk: {e}")
                    
            return iter([]) # Empty return stream

        return grpc.stream_stream_rpc_method_handler(stream_stream_handler)

class Command(BaseCommand):
    help = 'Runs the Telemetry Dial-out receiver server'
    def handle(self, *args, **options):
        server = grpc.server(futures.ThreadPoolExecutor(max_workers=50))
        server.add_generic_rpc_handlers((GenericReceiver(),))
        server.add_insecure_port('[::]:50000')
        self.stdout.write(self.style.SUCCESS('Starting Universal Telemetry Dial-Out receiver on port 50000...'))
        try:
            server.start()
            server.wait_for_termination()
        except KeyboardInterrupt:
            server.stop(0)
