"""Dev entrypoint: `python run.py`.""" #this is the entry point for running the FastAPI application in development mode. It allows you to start the server and test your application locally

import uvicorn  #this is same like the apache tomcat server in java but this is for python, it is used to run the fastapi application(python web framework) in development mode. It is a lightning-fast ASGI server implementation, using uvloop and httptools.

if __name__ == "__main__":
    uvicorn.run("app.main:app", host="0.0.0.0", port=8000, reload=True)
#this cant be imported in the main.py file because it will create a circular import error. 
#The main.py file is imported in this file, and if we import this file in main.py, 
#it will create a circular import error.
#uvicorn.run(...) this start the uvicorn server 

#                   "app.main:app"
#                Uvicorn is being told:
#        "Go to app/main.py and find the object called app.This main.py is in the project root ,app->init.py,main.py"
#local development happens in http://localhost:8000,as mentioned the port number is 8000
#reload=True = when we do changes in code,this automatically reload the server,we can disable it if we need to do