🚀 CareFinder
Find the Best Diabetes Hospital Near You
📌 Overview

CareFinder is a data-driven healthcare analytics web application designed to help users identify the best hospitals for Type 2 Diabetes care. The platform provides insights into hospital performance based on cost, insurance coverage, and patient visit trends, along with future predictions using machine learning models.

🎯 Problem Statement

Choosing the right hospital for diabetes care is complex due to:

Lack of transparent cost information
Variations in insurance coverage
No centralized system for comparison

CareFinder addresses this by providing a data-backed decision support system.

💡 Solution

CareFinder allows users to:

Filter hospitals by state and city
View top recommended hospitals
Compare multiple hospitals side-by-side
Analyze cost, coverage, and out-of-pocket expenses
View historical trends and future predictions
🧠 Key Features
🏠 Home Page
Overview dashboard with:
Total hospitals, patients, visits
Average cost & coverage
Interactive charts:
Gender distribution
Age group distribution
Insurance payer insights
State-wise hospital distribution
🔍 Recommendations Page
Displays:
Top hospitals based on visits
Top hospitals based on coverage
Best recommended hospitals (combined score)
🏥 Hospital Detail Page
Detailed hospital information
Cost breakdown:
Total cost
Coverage
Out-of-pocket
Predictive analytics:
Monthly & yearly forecasts
Future cost estimation
⚖️ Compare Hospitals
Compare up to 4 hospitals
Side-by-side comparison:
Cost
Coverage
Visits
Performance metrics
📊 Predictive Analytics
Forecast next 36 months
Smooth transition between historical & predicted values
Metrics:
Visits
Patients
Hospitals
Cost & coverage trends
🤖 Machine Learning Models
Random Forest
XGBoost
📦 Optimization
Models are pre-trained and stored as .pkl files
Eliminates runtime training → improves performance
🗂️ Data Pipeline
🔄 Data Source
Synthetic healthcare data generated using Synthea
⚙️ Flow
Generate data using Synthea
Upload ZIP batch
Validate CSV files
Store in Raw Tables
Sync to Master Tables
Generate Summary Tables
Train models → Save .pkl files
🧱 Database Design
MasterPatient
MasterHospital
MasterEncounter
🧠 Deduplication Logic
Based on:
patient_id
state
city
🛠️ Tech Stack
👨‍💻 Backend
Python 3.13
Django 6.x
🗄️ Database
MySQL (Primary)
PostgreSQL (Render deployment)
SQLite (Local testing)
📊 Data Processing
Pandas
NumPy
📈 Machine Learning
Scikit-learn
RandomForestRegressor
XGBoost
📉 Visualization
ApexCharts
Chart.js
Plotly
🎨 Frontend
Django Templates
HTML5 / CSS3
JavaScript
☁️ Deployment / Tools
Render (Cloud deployment)
GitHub (Version control)
ngrok (Public access from local)
📦 Dataset
Generated using:
run_synthea -p 2543 California -m "diabetes" -s 20474 --exporter.csv.export=true --exporter.fhir.export=false
Includes:
Patients
Encounters
Claims
Providers
Insurance data
⚡ Performance Optimization
Pre-trained .pkl models used instead of real-time training
Reduced page load time significantly
Efficient aggregation using summary tables
🔐 Note

Data shown in this application is synthetically generated using Synthea and does not represent real patient information.

🎓 Project Context
Developed as a Master’s Final Project (MRP)
Saint Louis University
Under guidance of Srikanth Mudigonda
🚀 Future Enhancements
Multi-disease support
Real-time hospital data integration
Advanced recommendation algorithms
User authentication & personalization
👨‍💻 Author

Ashok Medasani
📍 Saint Louis University
🔗 LinkedIn: https://www.linkedin.com/in/ashok-medasani/

⭐ Final Note

CareFinder is designed as a prototype healthcare decision system, demonstrating how data analytics and machine learning can improve hospital selection and cost transparency.
