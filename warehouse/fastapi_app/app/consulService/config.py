from os import environ
from dotenv import load_dotenv
import ifaddr
import socket
import requests
# Only needed for developing, on production Docker .env file is used

from consulService.get_uuid import uuid_random_string
load_dotenv()


class Config:
    """Set configuration vars from .env file."""
    CONSUL_HOST = environ.get("CONSUL_HOST", "consul")
    CONSUL_PORT = environ.get("CONSUL_PORT", 8500)
    CONSUL_DNS_PORT = environ.get("CONSUL_DNS_PORT", 8600)
    # Como lo deployeamos en aws se le pone el puerto de aws
    PORT = int(environ.get("SERVICE_PORT", '18014'))
    SERVICE_NAME = environ.get("SERVICE_NAME", "warehouse")
    SERVICE_ID = environ.get("SERVICE_ID", "warehouse") + "-" + uuid_random_string
    IP = None

    __instance = None

    @staticmethod
    def get_instance():
        if Config.__instance is None:
            Config()
        return Config.__instance

    def __init__(self):
        """ Virtually private constructor. """
        if Config.__instance is not None:
            raise Exception("This class is a singleton!")
        else:
            self.get_ip()
            Config.__instance = self

def get_ip(self):
    # AWS EC2 Metadata Service to get the local IP
    # TODO: Cambiar IP
    url_token = "http://169.254.169.254/latest/api/token"
    headers = {"X-aws-ec2-metadata-token-ttl-seconds": "21600"}
    try:
        response = requests.put(url_token, headers=headers)
        token = response.content.decode("utf-8")

        # Use the token to get the local IP
        # TODO: Cambiar IP
        url_ip = "http://169.254.169.254/latest/meta-data/local-ipv4"
        headers = {"X-aws-ec2-metadata-token": token}
        respuesta = requests.get(url_ip, headers=headers)
        self.IP = respuesta.content.decode("utf-8")
    except requests.RequestException as e:
        print(f"Error al obtener la IP desde AWS Metadata: {e}")
        self.IP = None  # Fall back if request fails

    # Default to localhost if IP is None
    if not self.IP:
        self.IP = "127.0.0.1"

@staticmethod
def get_adapter_ip(nice_name):
    adapters = ifaddr.get_adapters()

    for adapter in adapters:
        if adapter.nice_name == nice_name and len(adapter.ips) > 0:
            return adapter.ips[0].ip

    return None
