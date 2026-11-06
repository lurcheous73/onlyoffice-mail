#!/bin/bash
(
set -eu
app_password="$(cat /run/secrets/workspace_app)"
root_password="$(cat /run/secrets/workspace_root)"
[[ "$app_password" =~ ^[0-9a-f]{64}$ ]] && [[ "$root_password" =~ ^[0-9a-f]{64}$ ]] || exit 1
MYSQL_PWD="$root_password" mysql -uroot <<SQL
CREATE DATABASE onlyoffice CHARACTER SET utf8mb3 COLLATE utf8mb3_general_ci;
CREATE USER 'onlyoffice_user'@'%' IDENTIFIED WITH mysql_native_password BY '$app_password';
GRANT ALL ON onlyoffice.* TO 'onlyoffice_user'@'%';
ALTER USER 'root'@'%' IDENTIFIED WITH mysql_native_password BY '$root_password';
SQL
)
