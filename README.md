# CareFinder

## Find the Best Diabetes Hospital Near You

CareFinder is a data-driven healthcare analytics web application designed to help users identify suitable hospitals for Type 2 Diabetes care using synthetic healthcare data, cost analysis, insurance coverage insights, hospital visit trends, and machine learning-based future predictions.

## Overview

Choosing the right hospital for diabetes care can be difficult because patients often do not have clear information about hospital costs, insurance coverage, out-of-pocket expenses, and hospital usage patterns.

CareFinder solves this problem by providing a prototype decision-support platform where users can filter hospitals, compare options, view analytics, and understand future trends using predictive models.


## Problem Statement

Patients and healthcare decision-makers face challenges such as:

- Lack of transparent hospital cost information
- Differences in insurance coverage across providers
- Difficulty comparing hospitals side-by-side
- No centralized system for diabetes hospital recommendations
- Limited visibility into future hospital cost and visit trends

CareFinder addresses these issues through a data-backed recommendation and analytics system.

## Solution

CareFinder allows users to:

- Filter hospitals by state and city
- View top hospitals based on visits and insurance coverage
- Compare up to 4 hospitals side-by-side
- Analyze total cost, insurance coverage, and out-of-pocket expenses
- View historical hospital trends
- View future predictions for visits, patients, hospitals, cost, coverage, and out-of-pocket expenses

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

```bash
./run_synthea -p 2543 California -m diabetes -s 73921 --exporter.csv.export=true --exporter.fhir.export=false
