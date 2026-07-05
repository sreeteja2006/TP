import pandas as pd
import numpy as np
from typing import Dict, List, Tuple, Optional
import logging
from datetime import datetime, timedelta
import warnings
warnings.filterwarnings('ignore')

try:
    from prophet import Prophet
    PROPHET_AVAILABLE = True
except ImportError:
    PROPHET_AVAILABLE = False

try:
    from statsmodels.tsa.arima.model import ARIMA
    STATSMODELS_AVAILABLE = True
except ImportError:
    STATSMODELS_AVAILABLE = False

try:
    import tensorflow as tf
    from tensorflow.keras.models import Sequential
    from tensorflow.keras.layers import LSTM, Dense, Dropout
    from sklearn.preprocessing import MinMaxScaler
    TENSORFLOW_AVAILABLE = True
except ImportError:
    TENSORFLOW_AVAILABLE = False

try:
    from sklearn.ensemble import RandomForestRegressor
    from sklearn.preprocessing import StandardScaler
    SKLEARN_AVAILABLE = True
except ImportError:
    SKLEARN_AVAILABLE = False

logger = logging.getLogger(__name__)


class ProphetModel:
    def __init__(self):
        self.model = None
        self.is_trained = False

    def train(self, data: pd.DataFrame, target_column: str = 'Close') -> bool:
        if not PROPHET_AVAILABLE:
            return False
        try:
            prophet_data = pd.DataFrame({'ds': data.index, 'y': data[target_column]})
            self.model = Prophet(daily_seasonality=True, weekly_seasonality=True, yearly_seasonality=True, changepoint_prior_scale=0.05)
            self.model.fit(prophet_data)
            self.is_trained = True
            return True
        except Exception as e:
            logger.error(f'ProphetModel.train: {e}')
            return False

    def predict(self, steps: int) -> Optional[pd.DataFrame]:
        if not self.is_trained:
            return None
        try:
            future = self.model.make_future_dataframe(periods=steps)
            forecast = self.model.predict(future)
            return forecast[['ds', 'yhat', 'yhat_lower', 'yhat_upper']].tail(steps)
        except Exception as e:
            logger.error(f'ProphetModel.predict: {e}')
            return None


class ARIMAModel:
    def __init__(self, order: Tuple[int, int, int] = (1, 1, 1)):
        self.order = order
        self.fitted_model = None
        self.is_trained = False

    def train(self, data: pd.DataFrame, target_column: str = 'Close') -> bool:
        if not STATSMODELS_AVAILABLE:
            return False
        try:
            ts_data = data[target_column].dropna()
            self.fitted_model = ARIMA(ts_data, order=self.order).fit()
            self.is_trained = True
            return True
        except Exception as e:
            logger.error(f'ARIMAModel.train: {e}')
            return False

    def predict(self, steps: int) -> Optional[np.ndarray]:
        if not self.is_trained:
            return None
        try:
            forecast = self.fitted_model.forecast(steps=steps)
            return forecast.values if hasattr(forecast, 'values') else forecast
        except Exception as e:
            logger.error(f'ARIMAModel.predict: {e}')
            return None


class LSTMModel:
    def __init__(self, sequence_length: int = 60, units: int = 50):
        self.sequence_length = sequence_length
        self.units = units
        self.model = None
        self.scaler = None
        self.is_trained = False

    def train(self, data: pd.DataFrame, target_column: str = 'Close', epochs: int = 50) -> bool:
        if not TENSORFLOW_AVAILABLE:
            return False
        try:
            prices = data[target_column].values.reshape(-1, 1)
            self.scaler = MinMaxScaler()
            scaled = self.scaler.fit_transform(prices)
            X, y = self._create_sequences(scaled)
            if len(X) == 0:
                return False
            self.model = Sequential([
                LSTM(self.units, return_sequences=True, input_shape=(X.shape[1], 1)),
                Dropout(0.2),
                LSTM(self.units, return_sequences=False),
                Dropout(0.2),
                Dense(25),
                Dense(1)
            ])
            self.model.compile(optimizer='adam', loss='mean_squared_error')
            self.model.fit(X, y, batch_size=32, epochs=epochs, verbose=0)
            self.is_trained = True
            return True
        except Exception as e:
            logger.error(f'LSTMModel.train: {e}')
            return False

    def predict(self, data: pd.DataFrame, target_column: str = 'Close', steps: int = 1) -> Optional[np.ndarray]:
        if not self.is_trained:
            return None
        try:
            recent = data[target_column].tail(self.sequence_length).values.reshape(-1, 1)
            scaled = self.scaler.transform(recent)
            predictions = []
            seq = scaled.copy()
            for _ in range(steps):
                X = seq.reshape(1, self.sequence_length, 1)
                pred_scaled = self.model.predict(X, verbose=0)
                pred = self.scaler.inverse_transform(pred_scaled)[0, 0]
                predictions.append(pred)
                seq = np.roll(seq, -1)
                seq[-1] = pred_scaled
            return np.array(predictions)
        except Exception as e:
            logger.error(f'LSTMModel.predict: {e}')
            return None

    def _create_sequences(self, data: np.ndarray) -> Tuple[np.ndarray, np.ndarray]:
        X, y = [], []
        for i in range(self.sequence_length, len(data)):
            X.append(data[i - self.sequence_length:i, 0])
            y.append(data[i, 0])
        return np.array(X), np.array(y)


class RandomForestModel:
    def __init__(self, n_estimators: int = 100):
        self.n_estimators = n_estimators
        self.model = None
        self.scaler = None
        self.feature_columns = None
        self.is_trained = False

    def train(self, data: pd.DataFrame, target_column: str = 'Close') -> bool:
        if not SKLEARN_AVAILABLE:
            return False
        try:
            features_df = self._create_features(data).dropna()
            if len(features_df) == 0:
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
            'prophet': ProphetModel(),
            'arima': ARIMAModel(),
            'lstm': LSTMModel(),
            'random_forest': RandomForestModel()
        }
        self.weights = {'prophet': 0.3, 'arima': 0.2, 'lstm': 0.3, 'random_forest': 0.2}
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
                if name == 'prophet':
                    pred_df = model.predict(steps)
                    if pred_df is not None:
                        predictions[name] = pred_df['yhat'].values
                elif name == 'arima':
                    pred = model.predict(steps)
                    if pred is not None:
                        predictions[name] = pred
                elif name == 'lstm':
                    pred = model.predict(data, target_column, steps)
                    if pred is not None:
                        predictions[name] = pred
                elif name == 'random_forest':
                    pred = model.predict(data, steps)
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