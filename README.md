# Healthball

Healthball is a fullstack project exploring whether we can predict a soccer player's health and injury risk based on their
injury history, workload, and age. 

## Architecture
```
[ PostgreSQL (Neon) ] <--> [ FastAPI Backend + ML Model ] <--> [ React Frontend ]
```
* Database: Neon-hotsted Postgres for player & injury records
* Backend: FASTAPI serving ML predictions and player data
* Model: scikit-learn injury risk model (pickle)
* Frontend: React app for input & visualization
* Deployment: Render (backend), Vercel (frontend), Neon (DB)

## Project Structure
```
soccer-injury-prediction/
├── backend/        # FastAPI backend + ML model
├── frontend/       # React frontend
├── data/           # Injury datasets / CSVs
├── notebooks/      # Jupyter notebooks (EDA + training)
└── README.md
```

## Data
* Using publicly available datasets from Kaggle and Transfermarkt
* Synthetic data generated for prototyping
