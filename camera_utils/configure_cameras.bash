#!/usr/bin/env bash
# Set camera subsystem clocks to maximum rate on Jetson platforms.
# Compatible with JP5 (L4T r35.x) and JP6 (L4T r36.x).
# JP6/Orin may expose vi0/vi1 instead of vi.

BPMP_CLK=/sys/kernel/debug/bpmp/debug/clk

set_clk_max() {
    local name=$1
    local path="${BPMP_CLK}/${name}"
    if [ -d "${path}" ]; then
        local max_rate
        max_rate=$(cat "${path}/max_rate")
        echo "${max_rate}" > "${path}/rate"
        echo 1 > "${path}/mrq_rate_locked"
        echo "Set ${name} to ${max_rate} Hz (locked)"
    else
        echo "Note: clock '${name}' not found at ${path}, skipping"
    fi
}

# Common clocks (JP5 names; JP6/Orin may rename vi → vi0)
for clk in vi isp nvcsi vic emc; do
    set_clk_max "${clk}"
done

# JP6 Orin additional VI clocks
for clk in vi0 vi1; do
    set_clk_max "${clk}"
done
