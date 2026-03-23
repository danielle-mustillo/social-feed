CLUSTER_NAME ?= social-feed
NAMESPACE ?= social-feed
APP_IMAGE ?= social-feed:local
INGRESS_NGINX_MANIFEST ?= https://raw.githubusercontent.com/kubernetes/ingress-nginx/controller-v1.14.3/deploy/static/provider/cloud/deploy.yaml
METALLB_MANIFEST ?= https://raw.githubusercontent.com/metallb/metallb/v0.15.3/config/manifests/metallb-native.yaml
INGRESS_HOST ?= social-feed.local

.DEFAULT_GOAL := help

.PHONY: help up deploy ingress-ip test clean
.PHONY: _kind-create _install-metallb _install-ingress _install-networking
.PHONY: _image-load _schema-config _schema-init _bootstrap-data

help:
	@printf "Targets:\\n"
	@printf "  make up          # create the cluster and deploy the full stack with a 6-node Cassandra ring\\n"
	@printf "  make deploy      # rebuild and redeploy only the API against the current cluster\\n"
	@printf "  make ingress-ip  # print the ingress LoadBalancer IP\\n"
	@printf "  make test        # run the bash demo script against the ingress host\\n"
	@printf "  make clean       # delete the cluster and app resources\\n"

up: _kind-create _install-networking _bootstrap-data deploy

deploy: _image-load
	kubectl apply -f k8s/app.yaml
	kubectl apply -f k8s/ingress.yaml
	kubectl rollout restart deployment/social-feed-api -n $(NAMESPACE)
	kubectl -n $(NAMESPACE) rollout status deployment/social-feed-api --timeout=180s

ingress-ip:
	kubectl get svc ingress-nginx-controller -n ingress-nginx -o jsonpath='{.status.loadBalancer.ingress[0].ip}'; echo

test:
	@INGRESS_IP=$$(kubectl get svc ingress-nginx-controller -n ingress-nginx -o jsonpath='{.status.loadBalancer.ingress[0].ip}'); \
	test -n "$$INGRESS_IP"; \
	SOCIAL_FEED_BASE_URL=http://$$INGRESS_IP SOCIAL_FEED_HOST_HEADER=$(INGRESS_HOST) tests/smoke_live.sh

_kind-create:
	kind create cluster --name $(CLUSTER_NAME) --config k8s/kind-config.yaml

_install-metallb:
	kubectl apply -f $(METALLB_MANIFEST)
	kubectl wait --namespace metallb-system --for=condition=Available deployment/controller --timeout=180s
	kubectl rollout status --namespace metallb-system daemonset/speaker --timeout=180s
	kubectl apply -f k8s/metallb-config.yaml

_install-ingress:
	kubectl apply -f $(INGRESS_NGINX_MANIFEST)
	kubectl wait --namespace ingress-nginx --for=condition=Ready pod --selector=app.kubernetes.io/component=controller --timeout=180s

_install-networking: _install-metallb _install-ingress

_image-load:
	docker build -t $(APP_IMAGE) .
	kind load docker-image $(APP_IMAGE) --name $(CLUSTER_NAME)

_schema-config:
	kubectl create namespace $(NAMESPACE) --dry-run=client -o yaml | kubectl apply -f -
	kubectl -n $(NAMESPACE) create configmap social-feed-schema --from-file=schema.cql=schema.cql --dry-run=client -o yaml | kubectl apply -f -

_schema-init: _schema-config
	kubectl -n $(NAMESPACE) delete job social-feed-schema-init --ignore-not-found=true
	kubectl apply -f k8s/schema-job.yaml
	kubectl -n $(NAMESPACE) wait --for=condition=complete job/social-feed-schema-init --timeout=240s

_bootstrap-data: _schema-config
	kubectl apply -f k8s/namespace.yaml
	kubectl apply -f k8s/cassandra.yaml
	kubectl -n $(NAMESPACE) rollout status statefulset/cassandra-dc1-rack1 --timeout=1200s
	kubectl -n $(NAMESPACE) rollout status statefulset/cassandra-dc2-rack1 --timeout=1200s
	kubectl -n $(NAMESPACE) scale statefulset/cassandra-dc1-rack2 --replicas=1
	kubectl -n $(NAMESPACE) rollout status statefulset/cassandra-dc1-rack2 --timeout=1200s
	kubectl -n $(NAMESPACE) scale statefulset/cassandra-dc1-rack3 --replicas=1
	kubectl -n $(NAMESPACE) rollout status statefulset/cassandra-dc1-rack3 --timeout=1200s
	kubectl -n $(NAMESPACE) scale statefulset/cassandra-dc2-rack2 --replicas=1
	kubectl -n $(NAMESPACE) rollout status statefulset/cassandra-dc2-rack2 --timeout=1200s
	kubectl -n $(NAMESPACE) scale statefulset/cassandra-dc2-rack3 --replicas=1
	kubectl -n $(NAMESPACE) rollout status statefulset/cassandra-dc2-rack3 --timeout=1200s
	$(MAKE) _schema-init

clean:
	@$(SHELL) -lc 'if kind get clusters | grep -qx "$(CLUSTER_NAME)"; then \
		kubectl delete namespace $(NAMESPACE) --ignore-not-found=true --wait=false >/dev/null 2>&1 || true; \
		for pvc in $$(kubectl get pvc -n $(NAMESPACE) -o name 2>/dev/null); do \
			kubectl patch $$pvc -n $(NAMESPACE) --type=json -p='"'"'"'"'"'"'"'"'[{"op":"remove","path":"/metadata/finalizers"}]'"'"'"'"'"'"'"'"' >/dev/null 2>&1 || true; \
		done; \
		kubectl patch namespace $(NAMESPACE) --type=json -p='"'"'"'"'"'"'"'"'[{"op":"remove","path":"/spec/finalizers"}]'"'"'"'"'"'"'"'"' >/dev/null 2>&1 || true; \
		kind delete cluster --name $(CLUSTER_NAME); \
	else \
		kind delete cluster --name $(CLUSTER_NAME) >/dev/null 2>&1 || true; \
	fi'
