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

#### Using uv`` 
`uv sync`
`cd src/rag_app`
`uv run uvicorn main:app --reload --host 0.0.0.0 --port 8000`


## 2. Docker image
#### Build Docker image
`docker builder prune -f`
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

 ## 4. to AWS CloudWatch Logs Evluated
fields @timestamp, @message
| filter @message like /RAG_EVAL/
| parse @message "Question: * " as question
| parse @message "Context: * " as context
| parse @message "Answer: * " as answer
| sort @timestamp desc

W62ZTthTZ6A6prn
https://d14hbi7dyty7wy.cloudfront.net/chat
python -c "import sqlite3; conn = sqlite3.connect('kpi_data.db'); conn.execute('ALTER TABLE uploaded_reports ADD COLUMN report_period VARCHAR'); conn.execute('ALTER TABLE uploaded_reports ADD COLUMN period_label VARCHAR'); conn.commit(); conn.close(); print('Done!')"
sqlite3 kpi_data.db "DELETE FROM uploaded_reports WHERE id IN (4);
sqlite3 kpi_data.db "DELETE FROM weekly_notes;"

Sales: https://d14hbi7dyty7wy.cloudfront.net/dashboard
Admin (Track): https://d14hbi7dyty7wy.cloudfront.net/trackdashboard
Login: https://d14hbi7dyty7wy.cloudfront.net/dashboard/login



curl -X POST "https://d14hbi7dyty7wy.cloudfront.net/trackdashboard/users/create" \
  -u "ADMIN_USER:ADMIN_PASS" \
  -F "username=mohanad yehia" \
  -F "password=Elhonda123@#" \
  -F "role=admin"