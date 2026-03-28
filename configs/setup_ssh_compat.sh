#!/bin/bash
#
# SSH 兼容性配置脚本
# 
# 重要说明：
#   - 部分 Linux 发行版在编译时禁用了不安全的 SSH 算法
#   - 此脚本只能配置系统支持的算法
#   - 对于完全禁用的算法，需要使用项目内置的 paramiko 库
#

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"
SSH_CONFIG_FILE="$SCRIPT_DIR/ssh_config"

echo "==================================="
echo "SSH 兼容性配置脚本"
echo "==================================="
echo ""

# 检查当前用户
if [ "$EUID" -eq 0 ]; then 
   echo "⚠️  警告: 不建议使用 root 用户运行此脚本"
   echo "   建议使用普通用户运行"
   echo ""
fi

# 显示当前 SSH 版本
echo "🔍 当前 SSH 版本:"
ssh -V 2>&1
echo ""

# 检查系统支持的算法
echo "📌 系统支持的旧版算法:"
echo "   主机密钥: $(ssh -Q key 2>/dev/null | grep -E 'ssh-rsa|ssh-dss' | tr '\n' ' ')"
echo "   密钥交换: $(ssh -Q kex 2>/dev/null | grep -E 'group1|group14-sha1' | tr '\n' ' ')"
echo "   加密: $(ssh -Q cipher 2>/dev/null | grep -E 'cbc' | tr '\n' ' ')"
echo ""

# 配置文件路径
SYSTEM_SSH_CONFIG="/etc/ssh/ssh_config"
USER_SSH_CONFIG="$HOME/.ssh/config"

echo "📋 配置文件位置:"
echo "   系统配置: $SYSTEM_SSH_CONFIG"
echo "   用户配置: $USER_SSH_CONFIG"
echo "   项目配置: $SSH_CONFIG_FILE"
echo ""

# 函数：检查算法是否可用
check_algorithm() {
    ssh -Q "$1" 2>/dev/null | grep -q "$2"
}

# 函数：配置用户级 SSH
configure_user_ssh() {
    echo "🔧 配置用户级 SSH 兼容性..."
    
    # 创建 .ssh 目录
    mkdir -p "$HOME/.ssh"
    chmod 700 "$HOME/.ssh"
    
    # 检查是否已存在配置
    if [ -f "$USER_SSH_CONFIG" ]; then
        if grep -q "Network Management System" "$USER_SSH_CONFIG" 2>/dev/null; then
            echo "   ✅ 用户配置已存在，跳过"
            return
        fi
        
        # 备份旧配置
        backup_file="$USER_SSH_CONFIG.backup.$(date +%Y%m%d%H%M%S)"
        cp "$USER_SSH_CONFIG" "$backup_file"
        echo "   💾 已备份旧配置: $backup_file"
    fi
    
    # 检查系统支持的算法
    local host_key_algos=""
    local kex_algos=""
    local ciphers=""
    
    if check_algorithm key "ssh-rsa"; then
        host_key_algos="ssh-rsa,"
    fi
    if check_algorithm key "ssh-dss"; then
        host_key_algos="${host_key_algos}ssh-dss,"
    fi
    
    if check_algorithm kex "diffie-hellman-group14-sha1"; then
        kex_algos="diffie-hellman-group14-sha1,"
    fi
    if check_algorithm kex "diffie-hellman-group1-sha1"; then
        kex_algos="${kex_algos}diffie-hellman-group1-sha1,"
    fi
    
    if check_algorithm cipher "aes128-cbc"; then
        ciphers="aes128-cbc,aes192-cbc,aes256-cbc,3des-cbc"
    fi
    
    # 添加兼容性配置
    cat >> "$USER_SSH_CONFIG" << EOF

# Network Management System - SSH Compatibility Settings
# 添加于: $(date)
Host *
    # 启用旧版算法兼容性（如果系统支持）
EOF

    if [ -n "$host_key_algos" ]; then
        echo "    HostKeyAlgorithms $host_key_algos" >> "$USER_SSH_CONFIG"
        echo "    PubkeyAcceptedKeyTypes $host_key_algos" >> "$USER_SSH_CONFIG"
    fi
    
    if [ -n "$kex_algos" ]; then
        echo "    KexAlgorithms $kex_algos" >> "$USER_SSH_CONFIG"
    fi
    
    if [ -n "$ciphers" ]; then
        echo "    Ciphers $ciphers" >> "$USER_SSH_CONFIG"
    fi
    
    chmod 600 "$USER_SSH_CONFIG"
    echo "   ✅ 用户配置已更新: $USER_SSH_CONFIG"
}

# 函数：配置系统级 SSH
configure_system_ssh() {
    echo "🔧 配置系统级 SSH 兼容性..."
    
    if [ ! -w "$SYSTEM_SSH_CONFIG" ]; then
        echo "   ❌ 需要 root 权限才能修改系统配置"
        echo "   请运行: sudo $0 --system"
        return 1
    fi
    
    if grep -q "Network Management System" "$SYSTEM_SSH_CONFIG" 2>/dev/null; then
        echo "   ✅ 系统配置已存在，跳过"
        return
    fi
    
    cp "$SYSTEM_SSH_CONFIG" "$SYSTEM_SSH_CONFIG.backup.$(date +%Y%m%d%H%M%S)"
    echo "   💾 已备份系统配置"
    
    # 添加配置
    cat >> "$SYSTEM_SSH_CONFIG" << 'EOF'

# Network Management System - SSH Compatibility Settings
Host *
    HostKeyAlgorithms ssh-ed25519,ecdsa-sha2-nistp256,rsa-sha2-512,rsa-sha2-256,ssh-rsa,ssh-dss
    PubkeyAcceptedKeyTypes ssh-ed25519,ecdsa-sha2-nistp256,rsa-sha2-512,rsa-sha2-256,ssh-rsa,ssh-dss
    KexAlgorithms curve25519-sha256,ecdh-sha2-nistp256,diffie-hellman-group14-sha256,diffie-hellman-group14-sha1
    Ciphers chacha20-poly1305@openssh.com,aes128-ctr,aes256-ctr,aes128-cbc,3des-cbc
EOF
    
    echo "   ✅ 系统配置已更新: $SYSTEM_SSH_CONFIG"
}

# 函数：测试连接
test_connection() {
    echo ""
    echo "🧪 测试 SSH 配置..."
    
    # 检查配置文件语法
    if ssh -F "$SSH_CONFIG_FILE" -G localhost >/dev/null 2>&1; then
        echo "   ✅ 项目配置文件语法正确"
    else
        echo "   ❌ 项目配置文件语法错误"
    fi
    
    # 检查系统支持的算法
    echo ""
    echo "📋 当前生效的算法配置:"
    ssh -F "$SSH_CONFIG_FILE" -G localhost 2>/dev/null | grep "hostkeyalgorithms" | head -1 | cut -d' ' -f2- | tr ',' '\n' | head -5 | sed 's/^/     - /'
    echo "     ..."
}

# 函数：显示帮助
show_help() {
    cat << EOF
用法: $0 [选项]

选项:
    --user      配置用户级 SSH (~/.ssh/config) [默认]
    --system    配置系统级 SSH (/etc/ssh/ssh_config) [需要 sudo]
    --test      测试 SSH 配置
    --help      显示此帮助

示例:
    # 配置用户级 SSH
    $0 --user
    
    # 配置系统级 SSH (需要 root)
    sudo $0 --system
    
    # 只测试配置
    $0 --test

重要提示:
    - 部分算法（如 ssh-rsa）可能在系统级别被禁用
    - 项目的 Web SSH 终端已使用 paramiko 库处理兼容性
    - 命令行 SSH 可能无法连接部分旧设备
EOF
}

# 主逻辑
case "${1:---user}" in
    --user|-u)
        configure_user_ssh
        test_connection
        echo ""
        echo "==================================="
        echo "✅ 配置完成！"
        echo "==================================="
        echo ""
        echo "💡 重要提示:"
        echo "   项目的 Web SSH 终端已自动处理旧版设备兼容性"
        echo "   命令行 SSH 可能无法连接部分旧设备"
        echo ""
        ;;
    --system|-s)
        configure_system_ssh
        test_connection
        echo ""
        echo "==================================="
        echo "✅ 系统级配置完成！"
        echo "==================================="
        ;;
    --test|-t)
        test_connection
        ;;
    --help|-h)
        show_help
        ;;
    *)
        echo "未知选项: $1"
        show_help
        exit 1
        ;;
esac

echo ""
echo "📝 详细说明: $PROJECT_DIR/SSH_COMPATIBILITY.md"
