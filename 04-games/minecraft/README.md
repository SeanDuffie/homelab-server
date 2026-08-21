# Homelab Minecraft Infrastructure

## System Architecture

The mc-router container binds to host port 25565 and routes traffic to isolated backend containers via requested hostnames across the internal mc-network. Primary active servers maintain mc-router.auto-scale-down=false to run continuously. Archived worlds sleep after inactivity to eliminate RAM consumption.

To migrate an existing save, drop the world files into the host's ./data/world directory before initializing the container. Place a 64x64 server-icon.png in the ./data root to establish the multiplayer list icon.To access the live Java console, configure tty: true and stdin_open: true in your compose file. Execute docker attach <container_name> in your terminal. Detach without killing the server using Ctrl+P, then Ctrl+Q.

## Environment Types

| Loader | Description |
| --- | --- |
| Vanilla | Base Java game. No backend optimization or plugin support. |
| Paper | Optimized plugin server. Degrades vanilla redstone mechanics to save CPU cycles. |
| Folia | Multi-threaded Paper fork. Highly volatile plugin compatibility. |
| Fabric | Lightweight modloader. Preserves vanilla mechanics. Ideal for server-side optimization. |
| Forge / NeoForge | Heavy ecosystems for massive modpacks. NeoForge replaces Forge for versions 1.20.4+. |
| Bedrock | Windows/Console C++ client. Requires the Geyser/Floodgate plugins to connect to Java. |

## Discord Integration Policy

Deploy one unique Discord Application (e.g., "Reunion Server Bot") per active social hub. Share a single bot token across all archived worlds to prevent Discord member-list clutter. Create bots via the Discord Developer Portal, enable Privileged Gateway Intents, generate an OAuth2 token, and use the URL generator to invite the bot.

DiscordSRV operates as a hard whitelist by enabling Require linked account to play.

- Channels: Route global traffic to an admin-only channel, awards/deaths/join to a public chat, and link to an account verification channel.
- Voice: Proximity chat requires a dedicated Discord Voice Category containing a single muted Lobby channel.
- Role Sync: Map Discord Role IDs to in-game permission groups using the GroupRoleSynchronizationGroupsAndRolesToSync YAML node.

## Plugins, Scripts, & Backups

The custom configs.py script intercepts plugin configurations. It parses a .gitignore excluded .env file to inject secrets directly into live YAML nodes, and modifies server.properties for variables like difficulty=hard and simulation-distance=32.

For EssentialsX, update-check is disabled. The compass-towards-home-perm and confirm-home-overwrite features are enabled. You must configure teleport-delay (3-5 seconds) and define sethome-multiple limits to maintain transit balance.

The mc-backup sidecar container runs alongside active servers, executing restic compression for scheduled, tiered backup retention independent of the main server loop.