# Build Docker image
docker build -t my-rag-app .

# Run docker image

docker run -p 80:80 --env-file .env my-rag-app

# Push to dokcerhub
docker tag my-rag-app ebrahemhesham/rag-app:v1
docker push ebrahemhesham/rag-app:v1



