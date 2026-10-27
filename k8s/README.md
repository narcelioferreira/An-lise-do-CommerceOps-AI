# Kubernetes

```
k8s/base/              Deployment, Service, NetworkPolicy, HTTPRoute e ConfigMap
k8s/overlays/dev/      namespace commerceops-dev, 1 réplica
k8s/overlays/staging/  namespace commerceops-staging, 2 réplicas
```

Pré-requisitos do cluster: um Gateway `commerceops` no namespace `gateway-system` (Gateway API), com
TLS e limite global de requisições, e um Postgres com `db/init/` aplicado.

Os segredos nunca vão para o git. Crie o Secret antes do deploy:

```bash
kubectl create namespace commerceops-dev --dry-run=client -o yaml | kubectl apply -f -
kubectl -n commerceops-dev create secret generic commerceops-secrets \
  --from-literal=DATABASE_URL='postgresql://...' \
  --from-literal=ORDER_ID_HMAC_KEY="$(python -c 'import secrets; print(secrets.token_hex(32))')" \
  --from-literal=LLM_API_KEY='...' \
  --from-literal=LANGFUSE_PUBLIC_KEY='...' --from-literal=LANGFUSE_SECRET_KEY='...'
kubectl apply -k k8s/overlays/dev
```

Controles (detalhes em `docs/04_seguranca.md`): Pod Security Admission `restricted`, contêiner sem
root e somente leitura, sem capabilities, seccomp, sem token de service account, NetworkPolicy que
nega tudo por padrão e probes que não dependem do LLM nem do Langfuse. O CI valida os manifests com
`kustomize build` + `kubeconform`.
