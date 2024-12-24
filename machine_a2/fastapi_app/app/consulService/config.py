from os import environ
from dotenv import load_dotenv
import ifaddr
import socket
# Only needed for developing, on production Docker .env file is used
load_dotenv()


class Config:
    """Set configuration vars from .env file."""
    CONSUL_HOST = environ.get("CONSUL_HOST", "consul")
    CONSUL_PORT = environ.get("CONSUL_PORT", 8500)
    CONSUL_DNS_PORT = environ.get("CONSUL_DNS_PORT", 8600)
    PORT = int(environ.get("UVICORN_PORT", '8000'))
    SERVICE_NAME = environ.get("SERVICE_NAME", "machine")
    SERVICE_ID = environ.get("SERVICE_ID", "machine-1")
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
        if self.SERVICE_NAME == "consul":
            # Resolver el nombre de Consul a una IP válida
            try:
                resolved_ip = socket.gethostbyname(self.CONSUL_HOST)
                self.IP = resolved_ip
            except socket.gaierror as e:
                self.IP = "127.0.0.1"  # Asignar por defecto si no puede resolver
                print(f"Error resolviendo {self.CONSUL_HOST}: {e}")
        else:
            self.IP = Config.get_adapter_ip("eth0")
            if not self.IP:
                self.IP = "127.0.0.1"

    @staticmethod
    def get_adapter_ip(nice_name):
        adapters = ifaddr.get_adapters()

        for adapter in adapters:
            if adapter.nice_name == nice_name and len(adapter.ips) > 0:
                return adapter.ips[0].ip

        return None
