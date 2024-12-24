# -*- coding: utf-8 -*-
"""FastAPI router definitions."""
from fastapi import APIRouter, status, HTTPException
from .config import Config
import requests
import logging
from .BLConsul import get_consul_service, get_consul_service_replicas, get_consul_key_value_item, get_consul_service_catalog
    

logger = logging.getLogger(__name__)

config = Config.get_instance()

router = APIRouter(prefix='/{}/consul'.format(config.SERVICE_NAME))


# Get Service from consul by name and return  ######################################################
@router.get('/call/{external_service_name}')
async def external_service_response(external_service_name: str):
    logger.info(f"GET external service response from {external_service_name}")
    service = get_consul_service(external_service_name)
    service['Name'] = external_service_name

    if service is None:
        raise HTTPException(
            status.HTTP_404_NOT_FOUND,
            "The service does not exist or there is no healthy replica"
        )

    ret_message, status_code = call_external_service(service)

    return {
        "message": ret_message,
        "status_code": status_code
    }


@router.get(
    '/kv/{key}',
    summary="Get Consul item value for the given key",
    responses={
        status.HTTP_200_OK: {},
        status.HTTP_404_NOT_FOUND: {}
    },
    tags=["Consul", "KV"]

)
async def key_values(key: str):
    logger.info(f"GET {key} from value store")
    key, value = get_consul_key_value_item(key)
    if value is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Item not found")
    return {key: value}


@router.get('/catalog')
async def get_catalog():
    logger.info(f"GET consul catalog")
    catalog = get_consul_service_catalog()
    return catalog


@router.get('/services')
async def get_services_replicas():
    logger.info(f"GET consul services")
    replicas = get_consul_service_replicas()
    return replicas


def call_external_service(service):
    logger.debug(f"Calling external service: {service['Name']}")
    url = "http://{host}:{port}/{path}".format(
        host=service['Address'],
        port=service['Port'],
        path=service['Name']
    )
    try:
        response = requests.get(url)
    except requests.exceptions.ConnectionError:
        response = None

    if response:
        ret_message = {
            "caller": config.SERVICE_NAME,
            "callerURL": "{}:{}".format(config.IP, config.PORT),
            "answerer": service['Name'],
            "answererURL": "{}:{}".format(service['Address'], service['Port']),
            "response": response.text,
            "status_code": response.status_code
        }
        status_code = response.status_code
    else:
        raise HTTPException(status.HTTP_500_INTERNAL_SERVER_ERROR, "Could not get message")
    return ret_message, status_code