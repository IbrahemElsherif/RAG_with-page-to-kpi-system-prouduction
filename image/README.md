## 1. Run Locally (Python)
If you want to test without Docker:

`cd image`
#### Unix/macOS:
`source .venv/bin/activate`
#### Windows:
`.venv\Scripts\activate`

#### Install dependencies
`pip install -r requirements.txt`

#### Run the server
`cd image/src/rag_app`
`uvicorn main:app --reload --host 0.0.0.0 --port 8000`

#### Using uv 
`uv sync`
`cd src/rag_app`
`uv run uvicorn main:app --reload --host 0.0.0.0 --port 8000`


## 2. Docker image
#### Build Docker image
`cd image`
`docker build -t my-rag-app .`

#### Run docker image for testing
`docker run -p 80:80 --env-file .env my-rag-app`

## 3. Deployment to AWS (ECS & ECR)

#### Push to dockerhub

`docker login`
`docker tag my-rag-app ebrahemhesham/rag-app:v1`
`docker push ebrahemhesham/rag-app:v1`

#### Update AWS ECS Service

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
W62ZTthTZ6A6prn
https://d14hbi7dyty7wy.cloudfront.net/chat