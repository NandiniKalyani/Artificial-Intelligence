COMPOSE = docker compose -f deploy/compose/docker-compose.yml

.PHONY: up down logs ps restart clean check wait

up:
	$(COMPOSE) up -d

down:
	$(COMPOSE) down

wait:
	./scripts/wait-for-stack.sh

logs:
	$(COMPOSE) logs -f --tail=100

ps:
	$(COMPOSE) ps

restart:
	$(COMPOSE) restart

# drops the qdrant volume too, so everything indexed is gone
clean:
	$(COMPOSE) down -v

check:
	./scripts/check-secrets.sh
	./scripts/check-style.sh
