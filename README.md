# CurioClip Backend

This is the backend for the CurioClip project, built with Django, Celery, and PostgreSQL. It uses Docker and Docker Compose for easy setup and deployment.

## Project Structure

- `curioclip-backend/` — Django backend (this directory)

## Prerequisites

- [Docker](https://docs.docker.com/get-docker/)
- [Docker Compose](https://docs.docker.com/compose/install/)
- [Git](https://git-scm.com/) (for cloning the repository)

## Getting Started

### 1. Clone the Repository

```bash
git clone https://github.com/jasonsherman/curioclip-backend.git
cd curioclip-backend
```

### 2. Create a `.env` File

Create a `.env` file in the `backend/` directory with the following variables:

```env
CELERY_REDIS_HOST=redis
OPENAI_API_KEY=your_openai_key
OPENROUTER_API_KEY=your_openrouter_key
SUPABASE_JWT_SECRET=your_supabase_jwt_secret
SUPABASE_URL=your_supabase_url
SUPABASE_KEY=your_supabase_key
SUPABASE_ANON_KEY=your_supabase_anon_key
DB_NAME=your_db_name
DB_USER=your_db_user
DB_PASSWORD=your_db_password
DB_HOST=your_db_host
DB_PORT=5432
```

> **Note:**
> - For local development with Docker Compose, set `CELERY_REDIS_HOST=redis` and `DB_HOST=db` if you add a `db` service to your `docker-compose.yml`.
> - Make sure to use strong secrets in production.

### 3. Build and Start the Services

```bash
docker-compose up --build
```

This will start:
- Django app (on [http://localhost:8000](http://localhost:8000))
- Celery worker
- Celery beat
- Redis

## Stopping the Project

```bash
docker-compose down
```

## Useful Commands

- Run tests:
  ```bash
  docker-compose exec web python manage.py test
  ```
- Access Django shell:
  ```bash
  docker-compose exec web python manage.py shell
  ```

## Troubleshooting

- **Ports already in use:** Stop other services using ports 8000 or 6379.
- **.env issues:** Ensure your `.env` file is present and correctly filled.
- **Database connection errors:** Make sure your DB credentials are correct and the DB service is running.

## Additional Notes

- For production, set `DEBUG=False` and configure `ALLOWED_HOSTS` in `curioclip/settings.py`.

---

Feel free to open issues or contribute! 