# CareFinder

## Find the Best Diabetes Hospital Near You

CareFinder is a data-driven healthcare analytics web application designed to help users identify suitable hospitals for Type 2 Diabetes care using synthetic healthcare data, cost analysis, insurance coverage insights, hospital visit trends, and machine learning-based future predictions.

---

## Overview

Choosing the right hospital for diabetes care can be difficult because patients often do not have clear information about hospital costs, insurance coverage, out-of-pocket expenses, and hospital usage patterns.

CareFinder solves this problem by providing a prototype decision-support platform where users can filter hospitals, compare options, view analytics, and understand future trends using predictive models.

---

## Problem Statement

Patients and healthcare decision-makers face challenges such as:

- Lack of transparent hospital cost information
- Differences in insurance coverage across providers
- Difficulty comparing hospitals side-by-side
- No centralized system for diabetes hospital recommendations
- Limited visibility into future hospital cost and visit trends

CareFinder addresses these issues through a data-backed recommendation and analytics system.

---

## Solution

CareFinder allows users to:

- Filter hospitals by state and city
- View top hospitals based on visits and insurance coverage
- Compare up to 4 hospitals side-by-side
- Analyze total cost, insurance coverage, and out-of-pocket expenses
- View historical hospital trends
- View future predictions for visits, patients, hospitals, cost, coverage, and out-of-pocket expenses

---

## Key Features

### Home Page

The Home page provides an overview dashboard with:

- Total hospitals
- Total patients
- Total visits
- Average cost
- Average insurance coverage
- Gender distribution
- Age group distribution
- Insurance payer insights
- State-wise hospital distribution

---

### Recommendations Page

The Recommendations page displays:

- Top hospitals based on patient visits
- Top hospitals based on insurance coverage
- Best recommended hospitals using a combined score
- Filters for state, city, gender, and insurance payer

---

### Hospital Detail Page

The Hospital Detail page provides detailed hospital-level insights such as:

- Hospital summary metrics
- Total cost
- Insurance coverage
- Out-of-pocket expenses
- Patient visits
- Historical trends
- Monthly and yearly forecasts
- Future cost and coverage predictions

---

### Compare Hospitals

The Compare page allows users to compare up to 4 hospitals side-by-side using:

- Visits
- Total cost
- Insurance coverage
- Out-of-pocket expenses
- Unique patients
- Average cost
- Coverage percentage
- Balanced recommendation score

---

## Predictive Analytics

CareFinder uses machine learning models to forecast future trends for the next 36 months.

Forecasted metrics include:

- Visits
- Patients
- Hospitals
- Average cost
- Average coverage
- Average out-of-pocket expenses

The application uses pre-trained models saved as `.pkl` files to avoid runtime model training and improve page performance.

---

## Machine Learning Models

The project uses:

- Random Forest Regressor
- XGBoost Regressor

The models are trained using historical monthly hospital summary data and saved as pickle files.

---

## Data Source

CareFinder uses synthetic healthcare data generated using Synthea.

Important note:

The data used in this project is fully synthetic and does not represent real patients, real hospitals, or real clinical records.

---

## Synthea Data Generation

To generate Type 2 Diabetes patient data using Synthea, use the following command:

./run_synthea -p 1000 California -m diabetes -s 73921 --exporter.csv.export=true --exporter.fhir.export=false

---

## Skills Covered

CareFinder demonstrates a wide range of technical, analytical, and system design skills across multiple domains.

---

### Programming & Development

- Python (Core programming, data processing, backend logic)
- Django (Full-stack web development, MVC architecture)
- SQL (Data querying, joins, aggregation, optimization)
- JavaScript (Frontend interactivity, dynamic UI behavior)
- HTML5 & CSS3 (Responsive UI design, layout structuring)

---

### Data Engineering

- Data ingestion from structured CSV files
- Batch processing pipeline design
- ETL pipeline (Extract, Transform, Load)
- Data validation and cleaning
- Schema design and normalization
- Handling large synthetic datasets

---

### Database Management

- Relational database design
- PostgreSQL (Cloud deployment)
- MySQL (Primary database support)
- SQLite (Local development)
- Indexing and query optimization
- Multi-table architecture (Raw → Master → Summary layers)

---

### Data Analysis & Analytics

- Exploratory Data Analysis (EDA)
- Aggregation and summarization techniques
- KPI design (cost, coverage, visits, patients)
- Comparative analytics across hospitals
- Trend analysis (monthly & yearly)

---

### Machine Learning

- Supervised learning (Regression models)
- Random Forest Regressor
- XGBoost Regressor
- Model training and evaluation
- Feature engineering
- Time-series forecasting concepts
- Model persistence using `.pkl` files

---

### Predictive Analytics

- Forecasting future trends (36 months)
- Time-based data modeling
- Historical vs predicted data blending
- Performance optimization using pre-trained models

---

### Data Visualization

- Interactive dashboards
- Chart.js (dynamic charts)
- Plotly (advanced analytics visualization)
- ApexCharts (responsive graphs)
- Data storytelling through visuals

---

### System Design

- End-to-end application architecture
- Separation of concerns (Raw, Master, Summary layers)
- Scalable data pipeline design
- Modular Django app structure
- Efficient data flow management

---

### Backend Development

- REST-style data handling in Django
- Business logic implementation
- Data filtering and query optimization
- API-like response structuring for frontend

---

### Frontend Development

- Dynamic UI rendering using Django templates
- User input handling (filters, dropdowns)
- Interactive dashboards
- Light/Dark theme handling
- Responsive design principles

---

### DevOps & Deployment

- Git & GitHub (Version control)
- Render (Cloud deployment)
- Environment configuration using `.env`
- PostgreSQL cloud database integration
- ngrok (local tunneling for testing)
- Deployment troubleshooting and optimization

---

### Performance Optimization

- Pre-trained model usage (no runtime training)
- Use of summary tables for fast queries
- Efficient database design
- Reduced page load times
- Optimized data aggregation

---

### Data Generation & Simulation

- Synthetic data generation using Synthea
- Healthcare data simulation
- Controlled dataset generation using random seeds
- Scenario-based dataset creation

---

### Problem-Solving & Analytical Thinking

- Translating real-world healthcare problems into data models
- Designing decision-support systems
- Handling incomplete or simulated data scenarios
- Building scalable and reusable solutions

---

### Research & Domain Knowledge

- Understanding healthcare analytics
- Diabetes care data interpretation
- Cost and insurance analysis
- Hospital performance benchmarking

---

### Software Engineering Practices

- Modular code structure
- Reusable components
- Debugging and troubleshooting
- Version control workflows
- Documentation and project structuring

---

## Summary of Skills

This project demonstrates:

- Full-stack development
- Data engineering
- Machine learning
- Predictive analytics
- System design
- Cloud deployment

All integrated into a real-world healthcare analytics prototype.
