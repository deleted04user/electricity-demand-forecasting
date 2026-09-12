import joblib
import operator

# Load the model package
model_pkg = joblib.load('models/electricity_xgb_prediction_model.pkl')

# Display key metrics
print('=' * 50)
print('MODEL TRAINING RESULTS')
print('=' * 50)
print(f"Training Date: {model_pkg['training_date']}")
print(f"Training Period: {model_pkg['training_period']}")
print(f"Early-Stopping Period: {model_pkg['early_stopping_period']}")
print(f"Held-Out Test Period: {model_pkg['test_period']}")

print('\n' + '=' * 50)
print('TEST SET METRICS (held-out, unseen during training)')
print('=' * 50)
for metric, value in model_pkg['metrics'].items():
    print(f'{metric}: {value:.6f}')

print('\n' + '=' * 50)
print('TOP 5 IMPORTANT FEATURES')
print('=' * 50)
sorted_features = sorted(model_pkg['feature_importance'].items(), 
                        key=operator.itemgetter(1), 
                        reverse=True)[:5]
for i, (feat, imp) in enumerate(sorted_features, 1):
    print(f'{i}. {feat}: {imp:.6f}')

print('\n✅ MODEL SUCCESSFULLY TRAINED AND SAVED!')
print(f'Model file: models/electricity_xgb_prediction_model.pkl')
