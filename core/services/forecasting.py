import os
import pickle
from dataclasses import dataclass
from typing import Optional

import numpy as np
import pandas as pd
from django.conf import settings
from sklearn.ensemble import RandomForestRegressor
from sklearn.metrics import mean_absolute_error, mean_squared_error, r2_score

try:
    from xgboost import XGBRegressor
    XGBOOST_AVAILABLE = True
except Exception:
    XGBOOST_AVAILABLE = False

from core.models import ModelArtifact


@dataclass
class ForecastResult:
    train_monthly: pd.DataFrame
    future_monthly: pd.DataFrame
    partial_month_start: Optional[pd.Timestamp]
    model_used: str
    metric_used: str
    evaluation: dict
    fitted_model: object
    feature_columns: list


class TimeSeriesForecaster:
    def __init__(
        self,
        encounters_qs,
        years_back=3,
        months_ahead=18,
        model_name="random_forest",
        ignore_recent_months=1,
        test_size=0.2,
    ):
        self.encounters_qs = encounters_qs
        self.years_back = years_back
        self.months_ahead = months_ahead
        self.model_name = (model_name or "random_forest").lower().strip()
        self.ignore_recent_months = max(1, int(ignore_recent_months))
        self.test_size = float(test_size)

    def _get_model(self):
        if self.model_name == "xgboost" and XGBOOST_AVAILABLE:
            return XGBRegressor(
                n_estimators=300,
                max_depth=5,
                learning_rate=0.05,
                subsample=0.8,
                colsample_bytree=0.8,
                objective="reg:squarederror",
                random_state=42,
                n_jobs=-1,
            ), "XGBoost"

        return RandomForestRegressor(
            n_estimators=300,
            random_state=42,
            n_jobs=-1,
        ), "Random Forest"

    def _qs_to_df(self):
        rows = list(
            self.encounters_qs.values(
                "start",
                "patient_id",
                "hospital_id",
                "total_claim_cost",
                "payer_coverage",
                "out_of_pocket",
            )
        )

        if not rows:
            return pd.DataFrame(columns=[
                "start", "patient_id", "hospital_id",
                "total_claim_cost", "payer_coverage", "out_of_pocket"
            ])

        df = pd.DataFrame(rows)
        df["start"] = pd.to_datetime(df["start"], errors="coerce", utc=True).dt.tz_localize(None)
        df = df.dropna(subset=["start"]).copy()

        for col in ["total_claim_cost", "payer_coverage", "out_of_pocket"]:
            df[col] = pd.to_numeric(df[col], errors="coerce").fillna(0)

        return df

    def _build_monthly_series(self, metric="visits"):
        df = self._qs_to_df()
        if df.empty:
            return pd.DataFrame(columns=["month_start", "value"]), None

        df["month_start"] = df["start"].dt.to_period("M").dt.to_timestamp()

        if metric == "patients":
            monthly = df.groupby("month_start")["patient_id"].nunique().reset_index(name="value")
        elif metric == "hospitals":
            monthly = df.groupby("month_start")["hospital_id"].nunique().reset_index(name="value")
        elif metric == "avg_cost":
            monthly = df.groupby("month_start")["total_claim_cost"].mean().reset_index(name="value")
        elif metric == "avg_coverage":
            monthly = df.groupby("month_start")["payer_coverage"].mean().reset_index(name="value")
        elif metric == "avg_oop":
            monthly = df.groupby("month_start")["out_of_pocket"].mean().reset_index(name="value")
        else:
            monthly = df.groupby("month_start").size().reset_index(name="value")

        monthly = monthly.sort_values("month_start").reset_index(drop=True)
        if monthly.empty:
            return monthly, None

        unique_months = monthly["month_start"].sort_values().tolist()
        if len(unique_months) < self.ignore_recent_months:
            return pd.DataFrame(columns=["month_start", "value"]), pd.Timestamp(unique_months[0])

        forecast_start_month = pd.Timestamp(unique_months[-self.ignore_recent_months])
        monthly = monthly[monthly["month_start"] < forecast_start_month].copy()

        if monthly.empty:
            return monthly, forecast_start_month

        last_train_month = pd.Timestamp(monthly["month_start"].max())
        min_train_month = last_train_month - pd.DateOffset(months=36)
        monthly = monthly[monthly["month_start"] >= min_train_month].copy()
        monthly = monthly.sort_values("month_start").reset_index(drop=True)
        return monthly, forecast_start_month

    @staticmethod
    def _create_features(monthly_df):
        temp = monthly_df.copy().sort_values("month_start").reset_index(drop=True)
        if temp.empty:
            return temp

        temp["month_start"] = pd.to_datetime(temp["month_start"], errors="coerce")
        temp = temp.dropna(subset=["month_start"]).copy()
        temp["year"] = temp["month_start"].dt.year
        temp["month_num"] = temp["month_start"].dt.month
        temp["quarter"] = temp["month_start"].dt.quarter
        temp["time_index"] = np.arange(len(temp))
        temp["lag_1"] = temp["value"].shift(1)
        temp["lag_2"] = temp["value"].shift(2)
        temp["lag_3"] = temp["value"].shift(3)
        temp["lag_6"] = temp["value"].shift(6)
        temp["lag_12"] = temp["value"].shift(12)
        temp["roll_mean_3"] = temp["value"].shift(1).rolling(3).mean()
        temp["roll_mean_6"] = temp["value"].shift(1).rolling(6).mean()
        return temp.dropna().reset_index(drop=True)

    @staticmethod
    def _feature_cols():
        return [
            "time_index", "year", "month_num", "quarter",
            "lag_1", "lag_2", "lag_3", "lag_6", "lag_12",
            "roll_mean_3", "roll_mean_6",
        ]

    def _evaluate_predictions(self, y_true, y_pred):
        if len(y_true) == 0:
            return {"r2": None, "rmse": None, "mae": None}

        return {
            "r2": float(r2_score(y_true, y_pred)) if len(y_true) > 1 else None,
            "rmse": float(np.sqrt(mean_squared_error(y_true, y_pred))),
            "mae": float(mean_absolute_error(y_true, y_pred)),
        }

    def _recursive_forecast(self, monthly_train, model, feature_cols, forecast_start_month):
        hist = monthly_train[["month_start", "value"]].copy().sort_values("month_start").reset_index(drop=True)
        future_rows = []
        current_month = pd.Timestamp(forecast_start_month)

        for _ in range(self.months_ahead):
            month_num = current_month.month
            quarter = ((month_num - 1) // 3) + 1
            year = current_month.year
            time_index = len(hist)

            lag_1 = hist["value"].iloc[-1] if len(hist) >= 1 else 0
            lag_2 = hist["value"].iloc[-2] if len(hist) >= 2 else lag_1
            lag_3 = hist["value"].iloc[-3] if len(hist) >= 3 else lag_1
            lag_6 = hist["value"].iloc[-6] if len(hist) >= 6 else lag_1
            lag_12 = hist["value"].iloc[-12] if len(hist) >= 12 else lag_1
            roll_mean_3 = hist["value"].tail(3).mean() if len(hist) >= 3 else hist["value"].mean()
            roll_mean_6 = hist["value"].tail(6).mean() if len(hist) >= 6 else hist["value"].mean()

            row = pd.DataFrame([{
                "time_index": time_index,
                "year": year,
                "month_num": month_num,
                "quarter": quarter,
                "lag_1": lag_1,
                "lag_2": lag_2,
                "lag_3": lag_3,
                "lag_6": lag_6,
                "lag_12": lag_12,
                "roll_mean_3": roll_mean_3,
                "roll_mean_6": roll_mean_6,
            }])

            pred = max(0, float(model.predict(row[feature_cols])[0]))
            future_rows.append({"month_start": current_month, "forecast_value": pred})
            hist = pd.concat([hist, pd.DataFrame([{"month_start": current_month, "value": pred}])], ignore_index=True)
            current_month = current_month + pd.DateOffset(months=1)

        return pd.DataFrame(future_rows)

    def run(self, metric="visits"):
        monthly_train, partial_month_start = self._build_monthly_series(metric=metric)
        if monthly_train.empty or partial_month_start is None:
            return ForecastResult(
                train_monthly=pd.DataFrame(columns=["month_start", "value"]),
                future_monthly=pd.DataFrame(columns=["month_start", "forecast_value"]),
                partial_month_start=None,
                model_used=self.model_name,
                metric_used=metric,
                evaluation={},
                fitted_model=None,
                feature_columns=[],
            )

        feature_df = self._create_features(monthly_train)
        if feature_df.empty:
            return ForecastResult(
                train_monthly=monthly_train,
                future_monthly=pd.DataFrame(columns=["month_start", "forecast_value"]),
                partial_month_start=partial_month_start,
                model_used=self.model_name,
                metric_used=metric,
                evaluation={},
                fitted_model=None,
                feature_columns=[],
            )

        feature_cols = self._feature_cols()
        X = feature_df[feature_cols].copy()
        y = feature_df["value"].copy()
        month_labels = feature_df["month_start"].copy()

        n_rows = len(feature_df)
        test_count = max(1, int(round(n_rows * self.test_size)))
        if n_rows <= 6:
            test_count = 1
        if test_count >= n_rows:
            test_count = 1

        split_index = n_rows - test_count

        X_train = X.iloc[:split_index].copy()
        y_train = y.iloc[:split_index].copy()
        X_test = X.iloc[split_index:].copy()
        y_test = y.iloc[split_index:].copy()

        months_train = month_labels.iloc[:split_index].copy()
        months_test = month_labels.iloc[split_index:].copy()

        model, pretty_name = self._get_model()
        model.fit(X_train, y_train)

        train_pred = model.predict(X_train)
        test_pred = model.predict(X_test)

        train_metrics = self._evaluate_predictions(y_train, train_pred)
        test_metrics = self._evaluate_predictions(y_test, test_pred)

        full_model, _ = self._get_model()
        full_model.fit(X, y)

        future = self._recursive_forecast(monthly_train, full_model, feature_cols, partial_month_start)

        evaluation = {
            "train_metrics": train_metrics,
            "test_metrics": test_metrics,
            "train_actual_vs_pred": [
                {
                    "month_start": pd.Timestamp(m).strftime("%Y-%m-%d"),
                    "actual": float(a),
                    "predicted": float(p),
                    "residual": float(a - p),
                }
                for m, a, p in zip(months_train, y_train, train_pred)
            ],
            "test_actual_vs_pred": [
                {
                    "month_start": pd.Timestamp(m).strftime("%Y-%m-%d"),
                    "actual": float(a),
                    "predicted": float(p),
                    "residual": float(a - p),
                }
                for m, a, p in zip(months_test, y_test, test_pred)
            ],
            "dataset_summary": {
                "total_feature_rows": int(n_rows),
                "train_rows": int(len(X_train)),
                "test_rows": int(len(X_test)),
                "forecast_start_month": pd.Timestamp(partial_month_start).strftime("%Y-%m-%d"),
            },
        }

        return ForecastResult(
            train_monthly=monthly_train,
            future_monthly=future,
            partial_month_start=partial_month_start,
            model_used=pretty_name,
            metric_used=metric,
            evaluation=evaluation,
            fitted_model=full_model,
            feature_columns=feature_cols,
        )


def save_forecast_pickle(metric, model_name, trained_model_payload):
    artifact_dir = os.path.join(settings.MEDIA_ROOT, "pickles", metric)
    os.makedirs(artifact_dir, exist_ok=True)

    filename = f"{metric}_{model_name}.pkl"
    file_path = os.path.join(artifact_dir, filename)

    with open(file_path, "wb") as f:
        pickle.dump(trained_model_payload, f)

    ModelArtifact.objects.filter(metric=metric, is_active=True).update(is_active=False, replaced_at=pd.Timestamp.utcnow())
    ModelArtifact.objects.create(
        metric=metric,
        model_name=model_name,
        file_path=file_path,
        trained_from_months=36,
        forecast_months=18,
        source_note="master_data",
        is_active=True,
    )
    return file_path