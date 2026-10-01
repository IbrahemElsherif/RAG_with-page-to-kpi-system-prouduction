## 1. Run Locally (Python)

If you want to test without Docker:

```bash
cd image
```

#### Unix/macOS

```bash
source .venv/bin/activate
```

#### Windows

```powershell
.venv\Scripts\activate
```

#### Install dependencies

`requirements.txt` is a uv export kept for tooling that needs it; `uv sync` is the
supported path and the one the Docker build uses.

```bash
uv sync
```

#### Run the server

From `image/`:

```bash
cd src/rag_app
uv run uvicorn main:app --reload --host 0.0.0.0 --port 8000
```

`DB_PATH` and `CHROMA_PATH` in `.env` are relative and resolve against the application
directory, not the shell's working directory, so the same database is opened no matter
where you launch from.

## 2. Docker image

**All Docker commands run from the repo root, not `image/`.** `docker-compose.yaml`
owns the build context, image tag, port, env vars, volume mount and healthcheck, so
the image you test locally is byte-identical to the one you push.

Container paths mirror production: the EFS volume is mounted at **`/mnt/efs`** in ECS,
and compose bind-mounts `image/src/rag_app/data` to the same path.

### Build and test

```bash
docker compose build      # builds and tags ebrahemhesham/rag-app:v3
docker compose up         # http://localhost:8081
```

### Setting the version tag

The image tag comes from `$TAG`, defaulting to `v3`. **Set it once per shell session** —
the syntax differs, and the inline `TAG=v4 docker ...` form works only in bash:

| Shell      | Command             |
| ---------- | ------------------- |
| cmd.exe    | `set TAG=v4`      |
| PowerShell | `$env:TAG = "v4"` |
| bash / WSL | `export TAG=v4`   |

Confirm it took effect before building — this prints the tag compose will actually use:

```
docker compose config --images
```

## 3. Deployment to AWS (ECS & ECR)

Run these in order. `build` is what creates and tags the image; `push` uploads that exact
tag, so pushing before building has nothing to upload.

```
set TAG=v4                 (or the equivalent for your shell, above)

docker compose build       # 1. build and tag
docker compose up -d       # 2. verify on http://localhost:8081
docker login               # 3.
docker compose push        # 4. upload to DockerHub
```

### Verify a published image

Optional, and only *after* pushing — this replaces your local image with what DockerHub
actually holds, to prove the upload is good:

```
docker compose pull
docker compose up -d
```

Visit `http://localhost:8081` and confirm the app comes up before updating the ECS service.

> Compose builds for the host platform. Fargate here runs `LINUX/X86_64`, which matches
> an x86 Windows or Linux host. Building from an ARM Mac requires
> `platform: linux/amd64` on the service, or the task will not start.

### Update AWS ECS service

Update the task definition to reference the new image tag first, then:

```bash
aws ecs update-service --cluster default --service sstli-chatbot-spot --task-definition sstli-chatbot-v3 --force-new-deployment
```

### Create EFS mount targets (repeat for each subnet Fargate tasks run in)

```bash
aws efs create-mount-target \
    --file-system-id <fs-id> \
    --subnet-id <subnet-id> \
    --security-groups <security-group-id>
```

## 4. CloudWatch Logs Insights query (RAG eval)

```
fields @timestamp, question, context, answer
| filter log_type = "RAG_EVAL"
| sort @timestamp desc
```

## Production URLs

- Chat: https://d14hbi7dyty7wy.cloudfront.net/chat
- Sales dashboard: https://d14hbi7dyty7wy.cloudfront.net/dashboard
- Admin (Track): https://d14hbi7dyty7wy.cloudfront.net/trackdashboard
- Login: https://d14hbi7dyty7wy.cloudfront.net/dashboard/login

## Rag

chunking: chunk_size: int = 1000, chunk_overlap: int = 200
    splitting: recursive using RecursiveCharacterTextSplitter

Context:
    MEMORY_WINDOW_SIZE = 3
    SIMILARITY_THRESHOLD = 1.5
    TOP_K_RESULTS = 5

Generation:
   model="gpt-4o-mini" temperature=0
