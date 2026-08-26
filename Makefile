COMPOSE = docker compose -f deploy/compose/docker-compose.yml

.PHONY: up down logs ps restart clean check

up:
	$(COMPOSE) up -d

down:
	$(COMPOSE) down

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
