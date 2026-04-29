#!/usr/bin/env bash
# setup-ubuntu.sh — Installa tutti i requisiti del progetto su Ubuntu 22.04
# Esegui con: bash setup-ubuntu.sh
set -euo pipefail

GREEN='\033[0;32m'; YELLOW='\033[1;33m'; NC='\033[0m'
info()  { echo -e "${GREEN}[+]${NC} $*"; }
warn()  { echo -e "${YELLOW}[!]${NC} $*"; }

# ── 1. Aggiornamento sistema ──────────────────────────────────────────────────
info "Aggiornamento pacchetti di sistema..."
sudo apt-get update -qq
sudo apt-get install -y -qq \
    curl wget git ca-certificates gnupg lsb-release apt-transport-https

# ── 2. K3s (Kubernetes single-node) ──────────────────────────────────────────
info "Installazione K3s..."
curl -sfL https://get.k3s.io | sh -

# Rendi il kubeconfig accessibile all'utente corrente
mkdir -p "$HOME/.kube"
sudo cp /etc/rancher/k3s/k3s.yaml "$HOME/.kube/config"
sudo chown "$(id -u):$(id -g)" "$HOME/.kube/config"
chmod 600 "$HOME/.kube/config"

# Aggiunge KUBECONFIG al profilo shell
if ! grep -q "KUBECONFIG" "$HOME/.bashrc"; then
    echo 'export KUBECONFIG="$HOME/.kube/config"' >> "$HOME/.bashrc"
fi
export KUBECONFIG="$HOME/.kube/config"

info "Verifica K3s..."
sudo kubectl wait --for=condition=Ready node --all --timeout=60s

# ── 3. Helm 3 ────────────────────────────────────────────────────────────────
info "Installazione Helm 3..."
curl -fsSL https://raw.githubusercontent.com/helm/helm/main/scripts/get-helm-3 | bash

# ── 4. Docker (per build immagini in locale) ──────────────────────────────────
info "Installazione Docker..."
curl -fsSL https://get.docker.com | sudo sh
sudo usermod -aG docker "$USER"
warn "Docker installato. Esegui 'newgrp docker' o fai logout/login per usare docker senza sudo."

# ── 5. Repos Helm ────────────────────────────────────────────────────────────
info "Aggiunta repository Helm..."
helm repo add bitnami              https://charts.bitnami.com/bitnami
helm repo add chaos-mesh           https://charts.chaos-mesh.org
helm repo add ingress-nginx        https://kubernetes.github.io/ingress-nginx
helm repo add prometheus-community https://prometheus-community.github.io/helm-charts
helm repo update

# ── 6. Hosts ─────────────────────────────────────────────────────────────────
if ! grep -q "app.localhost" /etc/hosts; then
    info "Aggiunta app.localhost a /etc/hosts..."
    echo "127.0.0.1  app.localhost" | sudo tee -a /etc/hosts
fi

# ── 7. Riepilogo versioni ─────────────────────────────────────────────────────
echo ""
info "Installazione completata. Versioni installate:"
echo "  kubectl : $(kubectl version --client 2>/dev/null | head -1)"
echo "  helm    : $(helm version --short)"
echo "  docker  : $(docker --version)"
echo ""
warn "Riavvia la shell (o esegui: source ~/.bashrc) prima di procedere."
warn "Per il load test usa il loop bash nel README (nessuna installazione richiesta)."
