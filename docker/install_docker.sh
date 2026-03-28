#!/usr/bin/env bash
# install_docker.sh — Install Docker CE with NVIDIA runtime on Jetson (JetPack 6.x)
# Run as root or with sudo: sudo bash docker/install_docker.sh
# Must be run from the Robot/ repo root so that docker/daemon.json can be copied.
set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# ── 1. Skip if Docker is already installed ────────────────────────────────────
if command -v docker &>/dev/null; then
  echo "Docker is already installed: $(docker --version)"
  echo "Skipping installation. To reconfigure, run steps manually."
  exit 0
fi

# ── 2. Fix broken nvidia-l4t-* packages if present ───────────────────────────
# On some custom carrier boards (e.g. Avermedia D131), NVIDIA's dpkg post-install
# scripts fail with "does not match any known boards", leaving packages half-configured
# and blocking all apt operations. This step is a no-op on unaffected boards.
if dpkg --get-selections 2>/dev/null | grep -qv 'install$'; then
  echo "Checking for broken nvidia-l4t packages..."
  BROKEN_PKGS=(
    nvidia-l4t-bootloader
    nvidia-l4t-kernel
    nvidia-l4t-kernel-headers
    nvidia-l4t-kernel-oot-modules
    nvidia-l4t-display-kernel
    nvidia-l4t-kernel-oot-headers
    nvidia-l4t-kernel-dtbs
  )
  patched=0
  for pkg in "${BROKEN_PKGS[@]}"; do
    f="/var/lib/dpkg/info/${pkg}.postinst"
    if [ -f "$f" ] && grep -q 'board' "$f" 2>/dev/null; then
      cp "$f" "${f}.bak"
      printf '#!/bin/bash\nexit 0\n' > "$f"
      echo "  Patched $f"
      patched=1
    fi
  done
  if [ "$patched" -eq 1 ]; then
    echo "Running dpkg --configure -a to clear broken state..."
    dpkg --configure -a
    for pkg in "${BROKEN_PKGS[@]}"; do
      f="/var/lib/dpkg/info/${pkg}.postinst"
      [ -f "${f}.bak" ] && mv "${f}.bak" "$f" && echo "  Restored $f"
    done
  fi
fi

# ── 3. Install Docker from official APT repository ───────────────────────────
echo "Installing Docker prerequisites..."
apt-get update -q
apt-get install -y ca-certificates curl gnupg lsb-release

echo "Adding Docker GPG key..."
install -m 0755 -d /etc/apt/keyrings
curl -fsSL https://download.docker.com/linux/ubuntu/gpg \
  | gpg --dearmor -o /etc/apt/keyrings/docker.gpg
chmod a+r /etc/apt/keyrings/docker.gpg

echo "Adding Docker APT repository..."
echo "deb [arch=arm64 signed-by=/etc/apt/keyrings/docker.gpg] \
https://download.docker.com/linux/ubuntu $(lsb_release -cs) stable" \
  | tee /etc/apt/sources.list.d/docker.list > /dev/null

echo "Installing Docker CE..."
apt-get update -q
DEBIAN_FRONTEND=noninteractive apt-get install -y \
  docker-ce docker-ce-cli containerd.io \
  docker-buildx-plugin docker-compose-plugin

# ── 4. Install and configure NVIDIA container runtime ────────────────────────
echo "Installing NVIDIA container runtime..."
apt-get install -y nvidia-container nvidia-container-toolkit

echo "Configuring NVIDIA container runtime..."
cp "${SCRIPT_DIR}/daemon.json" /etc/docker/daemon.json

systemctl daemon-reload
systemctl enable --now docker

# ── 5. Add nvidia user to docker group ───────────────────────────────────────
usermod -aG docker nvidia
echo "Added 'nvidia' to the docker group (takes effect on next login)."

# ── 6. Done ──────────────────────────────────────────────────────────────────
echo ""
echo "Docker installed successfully: $(docker --version)"
echo "Default runtime: $(docker info 2>/dev/null | grep 'Default Runtime' || true)"
echo ""
echo "Log out and back in (or run 'newgrp docker') for group membership to take effect."
echo "Verify GPU access: docker run --rm ubuntu:22.04 nvidia-smi"
