#!/bin/bash
echo "$(date) - Restarting PM2 application: modbus_pump" >> /home/aph/modbus-client/pm2_restart.log
pm2 restart modbus_pump
