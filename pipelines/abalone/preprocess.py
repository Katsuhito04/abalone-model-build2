"""Feature engineers the abalone dataset."""
import argparse
import logging
import os
import pathlib
import requests
import tempfile
import time

import boto3
import numpy as np
import pandas as pd

from sklearn.compose import ColumnTransformer
from sklearn.impute import SimpleImputer
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler, OneHotEncoder

logger = logging.getLogger()
logger.setLevel(logging.INFO)
logger.addHandler(logging.StreamHandler())


# Since we get a headerless CSV file we specify the column names here.
feature_columns_names = [
    "sex",
    "length",
    "diameter",
    "height",
    "whole_weight",
    "shucked_weight",
    "viscera_weight",
    "shell_weight",
]
label_column = "rings"

feature_columns_dtype = {
    "sex": str,
    "length": np.float64,
    "diameter": np.float64,
    "height": np.float64,
    "whole_weight": np.float64,
    "shucked_weight": np.float64,
    "viscera_weight": np.float64,
    "shell_weight": np.float64,
}
label_column_dtype = {"rings": np.float64}


def merge_two_dicts(x, y):
    """Merges two dicts, returning a new copy."""
    z = x.copy()
    z.update(y)
    return z


if __name__ == "__main__":
    logger.debug("Starting preprocessing.")
    parser = argparse.ArgumentParser()
    parser.add_argument("--input-data", type=str, required=True)
    args = parser.parse_args()

    base_dir = "/opt/ml/processing"
    pathlib.Path(f"{base_dir}/data").mkdir(parents=True, exist_ok=True)
    input_data = args.input_data
    bucket = input_data.split("/")[2]
    key = "/".join(input_data.split("/")[3:])

    logger.info("Downloading data from bucket: %s, key: %s", bucket, key)
    fn = f"{base_dir}/data/abalone-dataset.csv"
    s3 = boto3.resource("s3")
    s3.Bucket(bucket).download_file(key, fn)

    logger.debug("Reading downloaded data.")
    df = pd.read_csv(
        fn,
        header=None,
        names=feature_columns_names + [label_column],
        dtype=merge_two_dicts(feature_columns_dtype, label_column_dtype),
    )
    os.unlink(fn)

    logger.debug("Defining transformers.")
    numeric_features = list(feature_columns_names)
    numeric_features.remove("sex")
    numeric_transformer = Pipeline(
        steps=[("imputer", SimpleImputer(strategy="median")), ("scaler", StandardScaler())]
    )

    categorical_features = ["sex"]
    categorical_transformer = Pipeline(
        steps=[
            ("imputer", SimpleImputer(strategy="constant", fill_value="missing")),
            ("onehot", OneHotEncoder(handle_unknown="ignore")),
        ]
    )

    preprocess = ColumnTransformer(
        transformers=[
            ("num", numeric_transformer, numeric_features),
            ("cat", categorical_transformer, categorical_features),
        ]
    )

    logger.info("Applying transforms.")
    y = df.pop("rings")
    X_pre = preprocess.fit_transform(df)
    y_pre = y.to_numpy().reshape(len(y), 1)

    X = np.concatenate((y_pre, X_pre), axis=1)

    logger.info("Splitting %d rows of data into train, validation, test datasets.", len(X))
    np.random.shuffle(X)
    train, validation, test = np.split(X, [int(0.7 * len(X)), int(0.85 * len(X))])

    logger.info("Writing out datasets to %s.", base_dir)
    pd.DataFrame(train).to_csv(f"{base_dir}/train/train.csv", header=False, index=False)
    pd.DataFrame(validation).to_csv(
        f"{base_dir}/validation/validation.csv", header=False, index=False
    )
    pd.DataFrame(test).to_csv(f"{base_dir}/test/test.csv", header=False, index=False)

    current_time_sec = int(round(time.time()))
    event_time_feature_name = "EventTime"
    df_fs = df.copy()
    df_fs[event_time_feature_name] = pd.Series([current_time_sec]*len(df_fs), dtype="float64")
    role = "arn:aws:iam::713931074333:role/service-role/AmazonSageMaker-ExecutionRole-20241006T170081"

    feature_definition = [
        {'FeatureName': 'sex', 'FeatureType': 'String'},
        {'FeatureName': 'length', 'FeatureType': 'Fractional'},
        {'FeatureName': 'diameter', 'FeatureType': 'Fractional'},
        {'FeatureName': 'height', 'FeatureType': 'Fractional'},
        {'FeatureName': 'whole_weight', 'FeatureType': 'Fractional'},
        {'FeatureName': 'shucked_weight', 'FeatureType': 'Fractional'},
        {'FeatureName': 'viscera_weight', 'FeatureType': 'Fractional'},
        {'FeatureName': 'shell_weight', 'FeatureType': 'Fractional'},
        {'FeatureName': 'EventTime', 'FeatureType': 'Fractional'}
    ]

    feature_group_name = 'case-feature-group-off'
    record_identifier_name = 'sex'
    event_time_name = 'EventTime'
    feature_description = "feature group for new items of Animation genre"
    

    sagemaker_client = boto3.client("sagemaker", region_name="us-east-1")
    featurestore_runtime = boto3.client(service_name='sagemaker-featurestore-runtime', region_name="us-east-1")
    sagemaker_client.create_feature_group(
            FeatureGroupName = feature_group_name,
            RecordIdentifierFeatureName = record_identifier_name,
            EventTimeFeatureName = event_time_name,
            FeatureDefinitions = feature_definition,
            Description = feature_description,
            OfflineStoreConfig = {"S3StorageConfig" : {"S3Uri" :"s3://case172774495900973/"}},
            RoleArn = role)
    
    for label in df_fs.columns:
        if df_fs.dtypes[label] == 'object':
            df_fs[label] = df_fs[label].astype("str").astype("string")

    time.sleep(60)

    featurestore_runtime.put_record(
        FeatureGroupName=feature_group_name,
        Record=[
            {'FeatureName': 'sex', 'ValueAsString': 'String'},
            {'FeatureName': 'length', 'ValueAsString': '11'},
            {'FeatureName': 'diameter', 'ValueAsString': '11'},
            {'FeatureName': 'height', 'ValueAsString': '11'},
            {'FeatureName': 'whole_weight', 'ValueAsString': '11'},
            {'FeatureName': 'shucked_weight', 'ValueAsString': '11'},
            {'FeatureName': 'viscera_weight', 'ValueAsString': '11'},
            {'FeatureName': 'shell_weight', 'ValueAsString': '11'},
            {'FeatureName': 'EventTime', 'ValueAsString': '11'}
        ]
    )
