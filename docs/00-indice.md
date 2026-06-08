# Chaos Engineering su Kubernetes

## Resilience Testing di un'Architettura a Microservizi

> **Corso:** Distributed Edge Programming - Università di Modena e Reggio Emilia  
> **A.A.:** 2025/2026  
> **Autore:** Leonardo Cavedoni

---

## Indice delle Lezioni

### Parte I - Fondamenti di Kubernetes

| #                                 | Titolo                     | Argomenti                                                        |
| --------------------------------- | -------------------------- | ---------------------------------------------------------------- |
| [01](01-kubernetes-fondamenti.md) | Introduzione a Kubernetes  | Containerizzazione, orchestrazione, storia, perché K8s           |
| [02](02-architettura-cluster.md)  | Architettura di un Cluster | Control plane, worker node, etcd, API server, scheduler, kubelet |
| [03](03-oggetti-kubernetes.md)    | Oggetti Kubernetes         | Pod, Deployment, Service, Ingress, ConfigMap, HPA, Namespace     |

### Parte II - Helm

| #                | Titolo                         | Argomenti                                  |
| ---------------- | ------------------------------ | ------------------------------------------ |
| [04](04-helm.md) | Helm - Package Manager per K8s | Chart, Values, Templates, Release, Bitnami |

### Parte III - Chaos Engineering

| #                             | Titolo                         | Argomenti                                         |
| ----------------------------- | ------------------------------ | ------------------------------------------------- |
| [05](05-chaos-engineering.md) | Principi del Chaos Engineering | Steady state, ipotesi, storia Netflix, fallacies  |
| [06](06-chaos-mesh.md)        | Chaos Mesh                     | CRD, tipi di esperimenti, architettura, dashboard |

### Parte IV - Sviluppo e Deploy

| #                             | Titolo                        | Argomenti                                              |
| ----------------------------- | ----------------------------- | ------------------------------------------------------ |
| [07](07-applicazione.md)      | L'Applicazione a Microservizi | FastAPI, PostgreSQL, Redis, Nginx, resilience patterns |
| [08](08-deploy-kubernetes.md) | Deploy su Kubernetes          | Helm chart custom, manifesti, Ingress Traefik          |

### Parte V - Componenti del Progetto

| #                               | Titolo                                 | Argomenti                                     |
| ------------------------------- | -------------------------------------- | --------------------------------------------- |
| [09](09-componenti-progetto.md) | Componenti del Progetto                | Stack completo, namespace, rete interna, K3s  |
| [10](10-osservabilita.md)       | Osservabilità con Prometheus e Grafana | Metriche, ServiceMonitor, dashboard, alerting |

### Parte VI - Realizzazione

| #                             | Titolo                   | Argomenti                                                    |
| ----------------------------- | ------------------------ | ------------------------------------------------------------ |
| [11](11-esperimenti-chaos.md) | I 5 Esperimenti di Chaos | Pod failure, network delay, partition, CPU stress, cascading |
| [12](12-conclusioni.md)       | Risultati e Conclusioni  | Analisi, steady state, lezioni apprese                       |

---

## Prerequisiti Consigliati

- Conoscenza base di Linux e terminale
- Nozioni di containerizzazione (Docker)
- Concetti fondamentali di networking (TCP/IP, DNS, HTTP)

## Come Usare Questa Documentazione

I file sono pensati per essere letti in ordine. Ogni lezione include:

- **Teoria** - concetti spiegati con esempi
- **Diagrammi** - architetture visive
- **Codice** - snippet reali del progetto
- **Comandi** - tutto eseguibile sul cluster del progetto
