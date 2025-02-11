import  mlflow
import  pickle
import  os
import  pandas as pd
import  numpy  as np
import  plotly.express as px
import  matplotlib.pyplot as plt
from    sklearn.ensemble        import RandomForestClassifier
from    sklearn.model_selection import RandomizedSearchCV
from    sklearn.model_selection import cross_validate
from    parser                  import get_arg_parser
from    load_params             import load_json
from    mlflow.models           import infer_signature
from    mlflow.pyfunc           import PythonModel


RANDOM_SEED = np.random.seed(0)


class CustomRandomForestClassifier(PythonModel):
    def __init__(self, model):
        self.model = model

    def predict(self, context, model_input, params=None):
        predict_method = params.get('predict_method')

        if predict_method == 'predict':
            return self.model.predict(model_input)
        elif predict_method == 'predict_proba':
            return self.model.predict_proba(model_input)
        elif predict_method == 'predict_log_proba':
            return self.model.predict_log_proba(model_input)
        else:
            raise ValueError(f'\n>>>>>>>>> The prediction method {predict_method} is not supported.')


def create_hyper_parameters_range(parameters: dict):
    range_n_estimators = np.arange(start=round(parameters.get('model_parameters')['n_estimators'][0], 2),
                                   stop=round(parameters.get('model_parameters')['n_estimators'][-1], 2),
                                   step=5
                                   )
    range_max_depth = np.arange(start=round(parameters.get('model_parameters')['max_depth'][0], 2),
                                stop=round(parameters.get('model_parameters')['max_depth'][-1], 2),
                                step=1
                                )
    range_min_samples_split = np.arange(start=round(parameters.get('model_parameters')['min_samples_split'][0], 2),
                                        stop=round(parameters.get('model_parameters')['min_samples_split'][-1], 2),
                                        step=0.1
                                        )
    range_min_samples_leaf = np.arange(start=round(parameters.get('model_parameters')['min_samples_leaf'][0], 2),
                                       stop=round(parameters.get('model_parameters')['min_samples_leaf'][-1], 2),
                                       step=1
                                       )
    param_distributions = {'n_estimators'     : range_n_estimators,
                           'max_depth'        : range_max_depth,
                           'min_samples_split': range_min_samples_split,
                           'min_samples_leaf' : range_min_samples_leaf
                          }

    return param_distributions


def calculate_feature_importance(model, importance=0):
    # Calculate feature importance (Gini)
    feat_importance    = model.feature_importances_
    df_feat_importance = pd.DataFrame({'feature':    model.feature_names_in_,
                                       'importance': feat_importance}
                                      ).sort_values('importance', ascending=True)

    plt.figure(figsize=(8, 4))
    plt.boxplot(x=df_feat_importance['importance'], vert=False)
    plt.xlabel('Importance')
    plt.title('Feature importance distribution')
    mlflow.log_figure(plt.gcf(), 'feature_importance_boxplot.png')

    df_feat_importance_no_zero = df_feat_importance[df_feat_importance['importance'] > importance]
    plt.figure(figsize=(8, 10))
    plt.barh(df_feat_importance_no_zero['feature'], df_feat_importance_no_zero['importance'])
    plt.xlabel('Importance')
    plt.ylabel('Features')
    plt.title(f'{df_feat_importance_no_zero.shape[0]} importance greater than 0')
    mlflow.log_figure(plt.gcf(), 'feature_importance_bar_plot.png')

    return df_feat_importance_no_zero


def plot_cross_validation_score(cv_results, score):
    # Create a line plot
    plot_fig, plot_ax = plt.subplots(figsize=(8, 4))
    plot_ax.plot(cv_results[f'train_{score}'],
                 marker='o',
                 linestyle='-',
                 color='blue',
                 label='Train'
                )
    plot_ax.plot(cv_results[f'test_{score}'],
                 marker='o',
                 linestyle='-',
                 color='red',
                 label='Validation'
                )
    plot_ax.set_xlabel('Iteration')
    plot_ax.set_xticks(range(1, len(cv_results[f'train_{score}']) + 1))
    plot_ax.set_ylabel('Score')
    plot_ax.set_title(f'Cross-validation {score} score')
    plot_ax.legend()
    plot_ax.grid(True)
    mlflow.log_figure(plot_fig, f'cv_{score}.png')


def train(dataframe_train: pd.DataFrame, parameters: dict):
    """
    The `train` function trains a RandomForestClassifier model on the provided training data, saves the
    model, and logs it using MLflow.
    
    :param dataframe_train: The `dataframe_train` parameter is a pandas DataFrame containing the
    training data for your machine learning model. It should include both the features and the target
    variable that you want to predict
    :type dataframe_train: pd.DataFrame
    :param parameters: {
    :type parameters: dict
    """

    print('#' * 80)
    print('TRAIN STARTED\n')

    # Split X and y train
    target   = parameters.get('target')
    dataframe_train[target] = dataframe_train[target].astype(float)
    features = dataframe_train.drop(columns=target).columns
    X_train  = dataframe_train[features]
    y_train  = dataframe_train[target]

    # Create and fit model
    # model = RandomForestClassifier(random_state=RANDOM_SEED, verbose=0)
    model_best_params = RandomForestClassifier(n_estimators=parameters.get('model_parameters')['n_estimators'],
                                               max_depth=parameters.get('model_parameters')['max_depth'],
                                               min_samples_split=parameters.get('model_parameters')['min_samples_split'],
                                               min_samples_leaf=parameters.get('model_parameters')['min_samples_leaf'],
                                               random_state=RANDOM_SEED,
                                               verbose=0
                                               )

    model_best_params.fit(X_train, y_train)
    # Save model
    model_data_path = os.path.join('train_artifacts', 'rf_clf.pkl')
    with open(model_data_path, 'wb') as f:
        pickle.dump(model_best_params, f, protocol=5)
    print(f'>>>>>>>>> model_best_params saved on {model_data_path}.')

    # Define model signature
    signature = infer_signature(model_input=X_train[:2], params={'predict_method': 'predict_proba'})
    mlflow.pyfunc.log_model(artifact_path=parameters.get('model_name'),
                            python_model=CustomRandomForestClassifier(model_best_params),
                            signature=signature
                            )

    print('\nTRAIN COMPLETED')
    print('#' * 80)


def main():
    args = get_arg_parser()
    # Load dataframes
    dataframe_train = pd.read_csv(args.path_dataframe_train,
                                  encoding='utf-8',
                                  sep=',',
                                  na_values=['na']
                                  )
    # Load params
    params = load_json(args.path_config_json)
    # Train model
    train(dataframe_train, params)


if __name__ == '__main__':
    main()
