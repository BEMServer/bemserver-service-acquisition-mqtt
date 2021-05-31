====================================
BEMServer service - acquisition MQTT
====================================

----------
Deployment
----------

It is recommended to manage the BEMServer service with systemd.

1. Create a ``bemserver-acquisition-mqtt.service`` configuration file in ``/etc/systemd/system/`` directory.

2. Copy the configuration below
    .. code-block::

        [Unit]
        Description=BEMServer service for timeseries acquisition through MQTT
        After=network-online.target

        [Service]
        Type=simple
        # Here adapt paths to your installation.
        ExecStart=/path/to/venv/bin/bs-acq-mqtt /path/to/service/config.json
        Restart=on-failure

        [Install]
        WantedBy=multi-user.target

3. Register and enable the service (it will be launched at every OS start)
    .. code-block::

        systemctl enabled bemserver-acquisition-mqtt.service
