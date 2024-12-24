# MONOLITH


## Start the project
```
git clone https://gitlab.com/master1473038/MONOLITH.git
cd MONOLITH
docker compose up --build 
```
## Components of the project

This project is intended to divide a monolithic app into many micro services, in this case 5

- Machine: Creates the pieces of the orders. **Listens on port 8001**
- Order: Handles the order. **Listens on port 8002**
- Delivery: In charge of the delivery process. **Listens on port 8003**
- Client: ... **Listens on port 8004**
- Payment: Gives information about the payment process. **Listens on port 8005**
- Gateway: Gateway intended for the user to use the API with limited acess **Listens on port 8000**
- Gateway2: Gateway for full acess to the other API's services, intended for debug use. **Listens on port 8006**


