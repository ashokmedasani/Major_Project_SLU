from pathlib import Path

REQUIRED_FILES = [
    "patients.csv",
    "encounters.csv",
    "observations.csv",
    "immunizations.csv",
    "providers.csv",
    "organizations.csv",
    "claims.csv",
    "claims_transactions.csv",
    "payers.csv",
    "payer_transitions.csv",
]

CHOSEN_COLS = {
    "patients": [
        "Id","BIRTHDATE","GENDER","RACE","ETHNICITY",
        "CITY","STATE","ZIP","LAT","LON",
        "INCOME","HEALTHCARE_EXPENSES","HEALTHCARE_COVERAGE"
    ],
    "encounters": [
        "Id","START","STOP","PATIENT","ORGANIZATION","PROVIDER","PAYER",
        "ENCOUNTERCLASS","CODE","DESCRIPTION",
        "BASE_ENCOUNTER_COST","TOTAL_CLAIM_COST","PAYER_COVERAGE"
    ],
    "observations": ["DATE","PATIENT","CODE","DESCRIPTION","VALUE","UNITS","TYPE"],
    "immunizations": ["DATE","PATIENT","ENCOUNTER","CODE","DESCRIPTION","BASE_COST"],
    "providers": ["Id","ORGANIZATION","SPECIALITY","CITY","STATE","ZIP","LAT","LON","ENCOUNTERS","PROCEDURES"],
    "organizations": ["Id","NAME","CITY","STATE","ZIP","LAT","LON","REVENUE","UTILIZATION"],
    "claims": [
        "Id","PATIENTID","PROVIDERID",
        "PRIMARYPATIENTINSURANCEID","SECONDARYPATIENTINSURANCEID",
        "SERVICEDATE","STATUS1","STATUS2","STATUSP",
        "OUTSTANDING1","OUTSTANDING2","OUTSTANDINGP",
        "HEALTHCARECLAIMTYPEID1","HEALTHCARECLAIMTYPEID2"
    ],
    "claims_transactions": [
        "ID","CLAIMID","PATIENTID","PROVIDERID","SUPERVISINGPROVIDERID",
        "TYPE","AMOUNT","METHOD","FROMDATE","TODATE","PLACEOFSERVICE",
        "PROCEDURECODE","UNITS","UNITAMOUNT",
        "PAYMENTS","ADJUSTMENTS","TRANSFERS","OUTSTANDING","PATIENTINSURANCEID"
    ],
    "payers": [
        "Id","NAME","OWNERSHIP","AMOUNT_COVERED","AMOUNT_UNCOVERED",
        "REVENUE","COVERED_ENCOUNTERS","UNCOVERED_ENCOUNTERS",
        "COVERED_IMMUNIZATIONS","UNCOVERED_IMMUNIZATIONS",
        "UNIQUE_CUSTOMERS","QOLS_AVG","MEMBER_MONTHS"
    ],
    "payer_transitions": [
        "PATIENT","PAYER","SECONDARY_PAYER","START_DATE","END_DATE",
        "MEMBERID","PLAN_OWNERSHIP","OWNER_NAME"
    ],
}

PROJECT_ROOT = Path(__file__).resolve().parents[2]
MEDIA_ROOT = PROJECT_ROOT / "media"
UPLOADS_DIR = MEDIA_ROOT / "uploads"
EXPORTS_DIR = MEDIA_ROOT / "exports"
LOGS_DIR = MEDIA_ROOT / "logs"