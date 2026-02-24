from unittest.mock import patch

import pytest


class TestMongoConfig:
    def test_config_standalone_defaults(self):
        from csp_lib.mongo.client import MongoConfig

        config = MongoConfig()
        assert config.host == "localhost"
        assert config.port == 27017
        assert not config.is_replica_set_mode

    def test_config_replica_hosts_without_set_raises(self):
        from csp_lib.mongo.client import MongoConfig

        with pytest.raises(ValueError, match="Replica Set"):
            MongoConfig(replica_hosts=("host1:27017",))

    def test_config_replica_set_without_hosts_raises(self):
        from csp_lib.mongo.client import MongoConfig

        with pytest.raises(ValueError, match="Replica Set"):
            MongoConfig(replica_set="mySet")

    def test_config_replica_set_valid(self):
        from csp_lib.mongo.client import MongoConfig

        config = MongoConfig(
            replica_hosts=("host1:27017", "host2:27017"),
            replica_set="mySet",
        )
        assert config.is_replica_set_mode

    @patch("csp_lib.mongo.client.AsyncIOMotorClient")
    def test_create_client_standalone(self, mock_motor):
        from csp_lib.mongo.client import MongoConfig, create_mongo_client

        config = MongoConfig(host="mongo.local", port=27017)
        create_mongo_client(config)
        mock_motor.assert_called_once()
        call_args = mock_motor.call_args
        assert "mongodb://mongo.local:27017" in call_args[0][0]

    @patch("csp_lib.mongo.client.AsyncIOMotorClient")
    def test_create_client_replica_set(self, mock_motor):
        from csp_lib.mongo.client import MongoConfig, create_mongo_client

        config = MongoConfig(
            replica_hosts=("host1:27017", "host2:27017"),
            replica_set="rs0",
        )
        create_mongo_client(config)
        call_args = mock_motor.call_args
        assert "host1:27017,host2:27017" in call_args[0][0]
        assert call_args[1]["replicaSet"] == "rs0"

    @patch("csp_lib.mongo.client.AsyncIOMotorClient")
    def test_create_client_with_auth(self, mock_motor):
        from csp_lib.mongo.client import MongoConfig, create_mongo_client

        config = MongoConfig(username="user", password="pass")
        create_mongo_client(config)
        call_args = mock_motor.call_args
        assert "user" in call_args[0][0]
        assert call_args[1]["authSource"] == "admin"

    @patch("csp_lib.mongo.client.AsyncIOMotorClient")
    def test_create_client_with_tls(self, mock_motor):
        from csp_lib.mongo.client import MongoConfig, create_mongo_client

        config = MongoConfig(tls=True, tls_ca_file="/path/to/ca.crt")
        create_mongo_client(config)
        call_args = mock_motor.call_args
        assert call_args[1]["tls"] is True
        assert call_args[1]["tlsCAFile"] == "/path/to/ca.crt"
