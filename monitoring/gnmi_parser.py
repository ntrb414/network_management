import re
from typing import Dict, Any

def _to_status(raw_value):
    if raw_value is None:
        return None
    text = str(raw_value).strip().lower()
    if text in {'up', '1', 'true'}:
        return 1
    if text in {'down', '2', 'false'}:
        return 2
    return None

def _to_int(raw_value):
    try:
        return int(raw_value)
    except (TypeError, ValueError):
        return None

def _extract_name(path_value):
    if isinstance(path_value, str):
        match = re.search(r'interface\[name=([^\]]+)\]', path_value)
        if match:
            return match.group(1)
        return None
    if not isinstance(path_value, dict):
        return None
    for elem in path_value.get('elem', []):
        if elem.get('name') != 'interface':
            continue
        key = elem.get('key', {})
        name = key.get('name')
        if name:
            return name
    return None

def flatten_metric_values(target: Dict[str, Any], value: Any):
    if isinstance(value, dict):
        for key, nested in value.items():
            if key in {'oper-status', 'admin-status', 'status'}:
                parsed_status = _to_status(nested)
                if parsed_status is not None:
                    target['status'] = parsed_status
            elif key == 'in-octets':
                in_octets = _to_int(nested)
                if in_octets is not None:
                    target['in_octets'] = in_octets
            elif key == 'out-octets':
                out_octets = _to_int(nested)
                if out_octets is not None:
                    target['out_octets'] = out_octets
            else:
                flatten_metric_values(target, nested)

def parse_gnmi_notification(notification: Dict[str, Any], interface_map: Dict[str, Dict[str, Any]]):
    # Parse a single notification dict and populate interface_map
    for update in notification.get('update', []):
        if not isinstance(update, dict):
            continue

        iface_name = _extract_name(update.get('path'))
        if not iface_name:
            continue

        iface_metrics = interface_map.setdefault(iface_name, {'name': iface_name})
        flatten_metric_values(iface_metrics, update.get('val'))

        path_str = str(update.get('path', ''))
        if 'oper-status' in path_str or 'status' in path_str:
            parsed_status = _to_status(update.get('val'))
            if parsed_status is not None:
                iface_metrics['status'] = parsed_status
        if 'in-octets' in path_str:
            in_octets = _to_int(update.get('val'))
            if in_octets is not None:
                iface_metrics['in_octets'] = in_octets
        if 'out-octets' in path_str:
            out_octets = _to_int(update.get('val'))
            if out_octets is not None:
                iface_metrics['out_octets'] = out_octets


def format_metrics_from_map(interface_map: Dict[str, Dict[str, Any]]) -> Dict[str, Any]:
    metrics = {
        'traffic': [],
        'packet_loss': None,
        'connections': None,
        'interfaces': [],
        'ospf_neighbors': [],
    }
    if interface_map:
        metrics['interfaces'] = list(interface_map.values())
        metrics['traffic'] = [
            {
                'interface': iface['name'],
                'in_octets': iface.get('in_octets', 0),
                'out_octets': iface.get('out_octets', 0),
                'is_first_collection': False,
            }
            for iface in metrics['interfaces']
            if iface.get('in_octets') is not None or iface.get('out_octets') is not None
        ]
    return metrics
