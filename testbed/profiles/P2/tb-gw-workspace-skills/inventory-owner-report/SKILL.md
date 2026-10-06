---
name: inventory-owner-report
description: Report which fictional inventory hosts each team owns, using the inventory-remote MCP server (testbed P2 gateway workspace skill).
---

# Inventory owner report

1. Call `inventory_list_hosts` on the `inventory-remote` MCP server.
2. For each host, call `inventory_get_host` and group the hosts by `owner`.
3. Reply with one line per owner team listing its hosts and roles.

Read only. Do not call any other server's tools.
