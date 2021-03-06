# FUTURE SERVICE PRINCIPAL STUFF FOR MOUNTING
secrets = {}
secrets["blob_name"] = dbutils.secrets.get(scope = "data-lake", key = "blob-name")
secrets["blob_key"] = dbutils.secrets.get(scope = "data-lake", key = "blob-key") 
secrets["container_name"] = dbutils.secrets.get(scope = "data-lake", key = "container-name")
secrets["subscription_id"] = dbutils.secrets.get(scope = "data-lake", key = "subscription-id")
secrets["resource_group"] = dbutils.secrets.get(scope = "data-lake", key = "resource-group")
secrets["ml_workspace_name"] = dbutils.secrets.get(scope = "data-lake", key = "ml-workspace-name")
secrets["alg_state"] = dbutils.secrets.get(scope = "data-lake", key = "alg-state")
try:
  secrets["created_by"] = dbutils.secrets.get(scope = "data-lake", key = "created-by")
except Exception as e:
  print("falling back to user set created_by")
  secrets["created_by"] = "dacrook"
           
#create the config variable to pass into mount
configs = {"fs.azure.account.key." + secrets["blob_name"] + ".blob.core.windows.net":"" + secrets["blob_key"] + ""}

#mounting the external blob storage as mount point datalake for data storage.
dbutils.fs.mount( source = "wasbs://" + secrets["container_name"] + "@" + secrets["blob_name"] + ".blob.core.windows.net/", 
                 mount_point = "/mnt/datalake/", 
                 extra_configs = configs)           

#display the files in the folder
dbutils.fs.ls("dbfs:/mnt/datalake")

census = sqlContext.read.format('csv').options(header='true', inferSchema='true').load('/mnt/datalake/AdultCensusIncome.csv')
census.printSchema()
display(census.select("age", " fnlwgt", " hours-per-week"))

import numpy as np
from sklearn.model_selection import train_test_split
from sklearn.preprocessing import StandardScaler
from sklearn.linear_model import LinearRegression
from sklearn.metrics import mean_absolute_error, r2_score
import pickle

x = np.array(census.select("age", " hours-per-week").collect()).reshape(-1,2)
y = np.array(census.select(" fnlwgt").collect()).reshape(-1,1)

#Split data & Train Scalers
x_train, x_test, y_train, y_test = train_test_split(x, y, test_size=0.33, random_state = 777, shuffle = True)
x_scaler = StandardScaler().fit(x_train)
y_scaler = StandardScaler().fit(y_train)

#Transform all data
x_train = x_scaler.transform(x_train)
x_test = x_scaler.transform(x_test)
y_train = y_scaler.transform(y_train)
y_test = y_scaler.transform(y_test)

model = LinearRegression().fit(x_train, y_train)

y_predicted = y_scaler.inverse_transform(model.predict(x_test))

mae = mean_absolute_error(y_test, y_predicted)
r2 = r2_score(y_test, y_predicted)

print(mae)
print(r2)

#Write Files to local file storage
import os
#Also works: "/dbfs/tmp/models/worst_regression/dacrook/"
prefix = "file:/models/worst_regression/"
if not os.path.exists(prefix):
  os.makedirs(prefix)
with open(prefix + "x_scaler.pkl", "wb") as handle:
  pickle.dump(x_scaler, handle)
with open(prefix + "y_scaler.pkl", "wb") as handle:
  pickle.dump(y_scaler, handle)
with open(prefix + "model.pkl", "wb") as handle:
  pickle.dump(model, handle)
  
#Create an Azure ML Model out of it tagged as dev
from azureml.core.workspace import Workspace
from azureml.core.authentication import ServicePrincipalAuthentication
from azureml.core.model import Model
print("Logging In - navigate to https://microsoft.com/devicelogin and enter the code from the print out below")
az_ws = Workspace(secrets["subscription_id"], secrets["resource_group"], secrets["ml_workspace_name"])
print("Logged in and workspace retreived.")
Model.register(az_ws, model_path = prefix, model_name = "worst_regression", tags={"state" : secrets["alg_state"], "created_by" : secrets["created_by"]})

#finally unmount the mount.
dbutils.fs.unmount("/mnt/datalake")
