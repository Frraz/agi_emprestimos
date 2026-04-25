.PHONY: up down restart logs build shell migrate collectstatic createsuperuser ps

# Sobe tudo
up:
	docker compose up -d

# Para tudo
down:
	docker compose down

# Restart do Django sem derrubar o banco
restart:
	docker compose restart web nginx

# Rebuild e sobe
build:
	docker compose build --no-cache
	docker compose up -d

# Logs em tempo real
logs:
	docker compose logs -f

logs-web:
	docker compose logs -f web

logs-nginx:
	docker compose logs -f nginx

# Shell dentro do container Django
shell:
	docker compose exec web python manage.py shell

# Bash dentro do container
bash:
	docker compose exec web /bin/sh

# Migrations
migrate:
	docker compose exec web python manage.py migrate

# Cria superuser
createsuperuser:
	docker compose exec web python manage.py createsuperuser

# Popular sistema (seed)
seed:
	docker compose exec web python manage.py popular_sistema

# Status dos containers
ps:
	docker compose ps

# Backup do banco
backup:
	docker compose exec db pg_dump -U $${DB_USER} $${DB_NAME} > backup_$$(date +%Y%m%d_%H%M%S).sql

# Limpa volumes (CUIDADO — apaga dados)
clean:
	docker compose down -v