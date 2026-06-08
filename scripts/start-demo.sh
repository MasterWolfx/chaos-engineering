#!/bin/bash
echo ">>> Avvio port-forward..."
kubectl port-forward -n app svc/frontend 8081:80 > /dev/null 2>&1 &
kubectl port-forward -n monitoring svc/monitoring-grafana 8082:80 > /dev/null 2>&1 &
kubectl port-forward -n chaos-mesh svc/chaos-dashboard 8083:2333 > /dev/null 2>&1 &

echo ">>> Attendo che i tunnel siano pronti..."
sleep 3

echo ">>> Tutto pronto!"
echo "    app.hypersoftware.it"
echo "    grafana.hypersoftware.it"
echo "    chaos.hypersoftware.it"
