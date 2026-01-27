## 1. Run Locally (Python)
If you want to test without Docker:

#### Install dependencies
`pip install -r requirements.txt`

#### Run the server
`sstli-chatbot/script/activate`
`cd image/src/rag_app`
`uvicorn main:app --reload --host 0.0.0.0 --port 8000`

## Using uv 
`uv sync`
`uv run uvicorn main:app --reload --host 0.0.0.0 --port 8000`


## 3. Docker image
#### Build Docker image
`cd image`
`docker build -t my-rag-app .`
#### Run docker image
`docker run -p 80:80 --env-file .env my-rag-app`

#### Push to dokcerhub
`docker tag my-rag-app ebrahemhesham/rag-app:v1`
`docker push ebrahemhesham/rag-app:v1`

## 4. Push to Docker Hub (For AWS)
`docker login`

#### Tag your local image to your Docker Hub repository
`docker tag my-rag-app ebrahemhesham/rag-app:v1`

#### Run docker compose
#### Push the image
`docker push ebrahemhesham/rag-app:v1`

#### Update AWS Service
```bash
aws ecs update-service \
   --cluster default \
   --service sstli-chatbot-spot \
   --force-new-deployment 
```

#### Create EFS (Repeat for each subnet ID where your Fargate tasks run)
```bash
aws efs create-mount-target \
    --file-system-id <fs-id> \
    --subnet-id <subnet-id> \
    --security-groups <security-group-id>
```