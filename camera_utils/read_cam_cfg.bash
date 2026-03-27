#!/usr/bin/env bash
# Read camera subsystem clock configuration on Jetson platforms.
# Compatible with JP5 (L4T r35.x) and JP6 (L4T r36.x).

BPMP_CLK=/sys/kernel/debug/bpmp/debug/clk

read_clk() {
    local name=$1
    local path="${BPMP_CLK}/${name}"
    if [ -d "${path}" ]; then
        echo "=== ${name} ==="
        echo "  max_rate:        $(cat ${path}/max_rate)"
        echo "  rate:            $(cat ${path}/rate)"
        echo "  mrq_rate_locked: $(cat ${path}/mrq_rate_locked)"
    fi
}

for clk in vi vi0 vi1 isp nvcsi vic emc; do
    read_clk "${clk}"
done
