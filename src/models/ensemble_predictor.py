import pandas as pd
import numpy as np
from typing import Dict, List, Tuple, Optional
import logging
import warnings
warnings.filterwarnings('ignore')

from statsmodels.tsa.arima.model import ARIMA
from sklearn.ensemble import RandomForestRegressor
from sklearn.preprocessing import StandardScaler

logger = logging.getLogger(__name__)


class ARIMAModel:
    def __init__(self, order: Tuple[int, int, int] = (5, 1, 0)):
        self.order = order
        self.fitted_model = None
        self.is_trained = False

    def train(self, data: pd.DataFrame, target_column: str = 'Close') -> bool:
        try:
            ts = data[target_column].dropna()
            self.fitted_model = ARIMA(ts, order=self.order).fit()
            self.is_trained = True
            return True
        except Exception as e:
            logger.error(f'ARIMAModel.train: {e}')
            return False

    def predict(self, steps: int) -> Optional[np.ndarray]:
        if not self.is_trained:
            return None
        try:
            fc = self.fitted_model.forecast(steps=steps)
            return fc.values if hasattr(fc, 'values') else fc
        except Exception as e:
            logger.error(f'ARIMAModel.predict: {e}')
            return None


class RandomForestModel:
    def __init__(self, n_estimators: int = 100):
        self.n_estimators = n_estimators
        self.model = None
        self.scaler = None
        self.feature_columns = None
        self.is_trained = False

    def train(self, data: pd.DataFrame, target_column: str = 'Close') -> bool:
        try:
            features_df = self._create_features(data).dropna()
            if len(features_df) < 30:
                return False
            X = features_df.drop(columns=[target_column])
            y = features_df[target_column]
            self.feature_columns = X.columns.tolist()
            self.scaler = StandardScaler()
            X_scaled = self.scaler.fit_transform(X)
            self.model = RandomForestRegressor(n_estimators=self.n_estimators, random_state=42, n_jobs=-1)
            self.model.fit(X_scaled, y)
            self.is_trained = True
            return True
        except Exception as e:
            logger.error(f'RandomForestModel.train: {e}')
            return False

    def predict(self, data: pd.DataFrame, steps: int = 1) -> Optional[np.ndarray]:
        if not self.is_trained:
            return None
        try:
            features_df = self._create_features(data)
            last = features_df[self.feature_columns].iloc[-1:].dropna()
            if len(last) == 0:
                return None
            X_scaled = self.scaler.transform(last)
            return np.full(steps, self.model.predict(X_scaled)[0])
        except Exception as e:
            logger.error(f'RandomForestModel.predict: {e}')
            return None

    def _create_features(self, data: pd.DataFrame) -> pd.DataFrame:
        df = data.copy()
        df['price_change'] = df['Close'].pct_change()
        df['price_change_2'] = df['Close'].pct_change(2)
        df['price_change_5'] = df['Close'].pct_change(5)
        df['sma_5'] = df['Close'].rolling(5).mean()
        df['sma_10'] = df['Close'].rolling(10).mean()
        df['sma_20'] = df['Close'].rolling(20).mean()
        df['volatility_5'] = df['Close'].rolling(5).std()
        df['volatility_10'] = df['Close'].rolling(10).std()
        if 'Volume' in df.columns:
            df['volume_change'] = df['Volume'].pct_change()
            df['volume_sma_5'] = df['Volume'].rolling(5).mean()
        return df


class EnsemblePredictor:
    def __init__(self):
        self.models = {
            'arima': ARIMAModel(),
            'random_forest': RandomForestModel()
        }
        self.weights = {'arima': 0.4, 'random_forest': 0.6}
        self.trained_models = []

    def train_all_models(self, data: pd.DataFrame, target_column: str = 'Close') -> Dict[str, bool]:
        results = {}
        self.trained_models = []
        for name, model in self.models.items():
            success = model.train(data, target_column)
            results[name] = success
            if success:
                self.trained_models.append(name)
        return results

    def predict_ensemble(self, data: pd.DataFrame, steps: int = 1, target_column: str = 'Close') -> Optional[Dict[str, np.ndarray]]:
        if not self.trained_models:
            return None
        predictions = {}
        for name in self.trained_models:
            model = self.models[name]
            try:
                if name == 'arima':
                    pred = model.predict(steps)
                elif name == 'random_forest':
                    pred = model.predict(data, steps)
                else:
                    pred = None
                if pred is not None:
                    predictions[name] = pred
            except Exception as e:
                logger.error(f'predict_ensemble [{name}]: {e}')

        if not predictions:
            return None
        predictions['ensemble'] = self._weighted_ensemble(predictions, steps)
        return predictions

    def _weighted_ensemble(self, predictions: Dict[str, np.ndarray], steps: int) -> np.ndarray:
        ensemble = np.zeros(steps)
        total_weight = 0.0
        for name, pred in predictions.items():
            if name in self.weights and len(pred) == steps:
                ensemble += self.weights[name] * pred
                total_weight += self.weights[name]
        return ensemble / total_weight if total_weight > 0 else ensemble

    def get_model_status(self) -> Dict[str, str]:
        return {name: ('Trained' if model.is_trained else 'Not Trained') for name, model in self.models.items()}