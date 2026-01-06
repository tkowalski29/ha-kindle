#!/usr/bin/env python3
import os
import json
from datetime import datetime
from flask import Flask, render_template, redirect, url_for, request
import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry
import websocket
import threading
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

app = Flask(__name__)

# Configuration from environment variables
HA_URL = os.getenv("HA_URL")
HA_WS_URL = os.getenv("HA_WS_URL")
HA_TOKEN = os.getenv("HA_TOKEN")

# UI Configuration
AUTO_REFRESH_INTERVAL = int(os.getenv("AUTO_REFRESH_INTERVAL", "0"))
THEME = os.getenv("THEME", "light")
GRID_COLUMNS = os.getenv("GRID_COLUMNS", "auto")
SHOW_BACK_BUTTON = os.getenv("SHOW_BACK_BUTTON", "true").lower() == "true"
SHOW_LAST_UPDATE = os.getenv("SHOW_LAST_UPDATE", "true").lower() == "true"

# Validate required environment variables
if not all([HA_URL, HA_WS_URL, HA_TOKEN]):
    raise ValueError("Missing required environment variables. Please check your .env file.")

# Create session with retry logic
session = requests.Session()
retry = Retry(connect=3, backoff_factor=0.5)
adapter = HTTPAdapter(max_retries=retry)
session.mount('http://', adapter)
session.mount('https://', adapter)

# WebSocket client cache
ws_lock = threading.Lock()
ws_message_id = 1


def get_ha_headers():
    return {
        "Authorization": f"Bearer {HA_TOKEN}",
        "Content-Type": "application/json",
    }


def get_states():
    """Get all states from Home Assistant"""
    response = session.get(f"{HA_URL}/api/states", headers=get_ha_headers())
    response.raise_for_status()
    return response.json()


def get_state(entity_id):
    """Get state of a specific entity"""
    response = session.get(
        f"{HA_URL}/api/states/{entity_id}", headers=get_ha_headers()
    )
    response.raise_for_status()
    return response.json()


def call_service(domain, service, entity_id):
    """Call a Home Assistant service"""
    response = session.post(
        f"{HA_URL}/api/services/{domain}/{service}",
        headers=get_ha_headers(),
        json={"entity_id": entity_id},
    )
    response.raise_for_status()
    return response.json()


def render_template_ha(template):
    """Render a Jinja2 template using Home Assistant"""
    response = session.post(
        f"{HA_URL}/api/template",
        headers=get_ha_headers(),
        json={"template": template},
    )
    response.raise_for_status()
    return response.json()


def get_areas():
    """Get all areas from Home Assistant"""
    area_ids = render_template_ha("{{ areas() | tojson }}")
    areas = []
    for area_id in area_ids:
        name = render_template_ha(f"{{{{ area_name('{area_id}') | tojson }}}}")
        if name and name != "null":
            areas.append({"id": area_id, "name": name})
    return areas


def get_entities_by_area(area_id):
    """Get entities for a specific area"""
    if area_id == "all":
        template = "{{ states | map(attribute='entity_id') | list | tojson }}"
    else:
        template = f"{{{{ area_entities('{area_id}') | tojson }}}}"
    return render_template_ha(template)


def ws_send_command(command_type, **params):
    """Send a command via WebSocket and get the response"""
    global ws_message_id

    with ws_lock:
        ws = websocket.create_connection(HA_WS_URL)

        try:
            # Receive auth_required message
            auth_msg = json.loads(ws.recv())

            # Send auth
            ws.send(json.dumps({
                "type": "auth",
                "access_token": HA_TOKEN
            }))

            # Receive auth_ok
            auth_result = json.loads(ws.recv())
            if auth_result.get("type") != "auth_ok":
                raise Exception("Authentication failed")

            # Send command
            msg_id = ws_message_id
            ws_message_id += 1

            command = {
                "id": msg_id,
                "type": command_type,
            }
            command.update(params)

            ws.send(json.dumps(command))

            # Receive response
            response = json.loads(ws.recv())

            ws.close()

            if not response.get("success"):
                error = response.get("error", {})
                raise Exception(f"Command failed: {error.get('code')} - {error.get('message')}")

            return response.get("result")

        except Exception as e:
            ws.close()
            raise e


def get_lovelace_dashboards():
    """Get list of Lovelace dashboards"""
    try:
        result = ws_send_command("lovelace/dashboards/list")
        return result if result else []
    except Exception as e:
        print(f"Error getting Lovelace dashboards: {e}")
        return []


def get_lovelace_config(url_path=None):
    """Get Lovelace dashboard config"""
    try:
        params = {}
        if url_path:
            params["url_path"] = url_path
        return ws_send_command("lovelace/config", **params)
    except Exception as e:
        print(f"Error getting Lovelace config: {e}")
        return None


def get_lovelace_views():
    """Get all Lovelace dashboard views"""
    dashboards = get_lovelace_dashboards()
    views = []

    for dashboard in dashboards:
        dashboard_id = dashboard.get("id", "")
        dashboard_title = dashboard.get("title", dashboard_id)

        # Try different url_path formats
        url_paths = [
            dashboard_id.replace("_", "-"),
            dashboard_id.replace("dashboard_", ""),
            dashboard_id,
        ]

        config = None
        for url_path in url_paths:
            config = get_lovelace_config(url_path)
            if config:
                break

        if not config:
            # Can't get config, add dashboard without views
            views.append({
                "title": dashboard_title,
                "path": f"lovelace-{dashboard_id}",
            })
            continue

        # Extract views from config
        dashboard_views = config.get("views", [])

        if not dashboard_views:
            # No views, add dashboard itself
            views.append({
                "title": dashboard_title,
                "path": f"lovelace-{dashboard_id}",
            })
            continue

        # Add each view as separate entry
        for view in dashboard_views:
            view_path = view.get("path", "")
            view_title = view.get("title", view_path)

            if not view_path:
                view_path = view_title
            if not view_title:
                view_title = view_path

            views.append({
                "title": view_title,
                "path": f"lovelace-{dashboard_id}-{view_path}",
            })

    return views


def get_icon_for_entity(domain, state):
    """Get icon for entity based on domain and state"""
    icons = {
        "light": {"on": "💡", "off": "⚫"},
        "switch": {"on": "🔘", "off": "⚪"},
        "fan": {"on": "🌀", "off": "⭕"},
        "cover": {"open": "📂", "closed": "📁"},
        "climate": {"any": "🌡️"},
        "sensor": {"any": "📊"},
    }

    if domain in icons:
        if state in icons[domain]:
            return icons[domain][state]
        elif "any" in icons[domain]:
            return icons[domain]["any"]

    return "❓"


def filter_entities(states, entity_ids=None, filter_types=True):
    """Filter states to get relevant entities"""
    entities = []

    # Convert entity_ids to set for faster lookup
    entity_id_set = set(entity_ids) if entity_ids else None

    for state in states:
        # Filter by entity ID if provided
        if entity_id_set and state["entity_id"] not in entity_id_set:
            continue

        domain = state["entity_id"].split(".")[0]

        # Filter by domain type
        if filter_types and domain not in ["light", "switch", "fan", "cover", "climate", "sensor"]:
            continue

        # Get friendly name
        name = state["attributes"].get("friendly_name", state["entity_id"])

        # Get icon
        icon = get_icon_for_entity(domain, state["state"])

        entities.append({
            "id": state["entity_id"],
            "name": name,
            "state": state["state"],
            "type": domain,
            "icon": icon,
            "attributes": state["attributes"],
        })

    return entities


@app.route("/")
def home():
    view = request.args.get("view", "rooms")

    if view == "dashboards":
        # Get Lovelace dashboard views
        dashboards = get_lovelace_views()
    else:
        # Get areas as rooms
        areas = get_areas()

        # Add icons based on area ID
        dashboards = []
        for area in areas:
            icon = "📍"
            if area["id"] == "kuchnia":
                icon = "🍳"
            elif area["id"] == "bathroom":
                icon = "🚿"
            elif area["id"] == "office":
                icon = "💼"
            elif area["id"] in ["balcony", "tarace"]:
                icon = "🌿"

            dashboards.append({
                "title": area["name"],
                "path": f"area-{area['id']}",
                "icon": icon,
            })

    return render_template(
        "home.html",
        dashboards=dashboards,
        current_view=view,
        auto_refresh=AUTO_REFRESH_INTERVAL,
        theme=THEME,
    )


def get_entities_from_lovelace_view(dashboard_id, view_path):
    """Extract entity IDs from a specific Lovelace view"""
    # Try different url_path formats
    url_paths = [
        dashboard_id.replace("_", "-"),
        dashboard_id.replace("dashboard_", ""),
        dashboard_id,
    ]

    config = None
    for url_path in url_paths:
        config = get_lovelace_config(url_path)
        if config:
            break

    if not config:
        return None

    # Find the specific view
    views = config.get("views", [])
    target_view = None

    for view in views:
        v_path = view.get("path", "")
        v_title = view.get("title", "")
        if v_path == view_path or v_title == view_path:
            target_view = view
            break

    if not target_view:
        return None

    # Extract entity IDs from cards
    entity_ids = []

    # Check if this is a sections-type view (newer format)
    if target_view.get("type") == "sections" and "sections" in target_view:
        for section in target_view.get("sections", []):
            cards = section.get("cards", [])
            for card in cards:
                extract_entities_from_card(card, entity_ids)
    else:
        # Traditional cards format
        cards = target_view.get("cards", [])
        for card in cards:
            extract_entities_from_card(card, entity_ids)

    return entity_ids if entity_ids else None


def extract_entities_from_card(card, entity_ids):
    """Extract entity IDs from a card and add them to entity_ids list"""
    # Get single entity from card
    if "entity" in card:
        entity_ids.append(card["entity"])

    # Get entities list from card
    if "entities" in card:
        for entity in card["entities"]:
            if isinstance(entity, str):
                entity_ids.append(entity)
            elif isinstance(entity, dict) and "entity" in entity:
                entity_ids.append(entity["entity"])


def get_lovelace_view_structure(dashboard_id, view_path):
    """Get full Lovelace view structure with sections and cards"""
    # Try different url_path formats
    url_paths = [
        dashboard_id.replace("_", "-"),
        dashboard_id.replace("dashboard_", ""),
        dashboard_id,
    ]

    config = None
    for url_path in url_paths:
        config = get_lovelace_config(url_path)
        if config:
            break

    if not config:
        return None

    # Find the specific view
    views = config.get("views", [])
    target_view = None

    for view in views:
        v_path = view.get("path", "")
        v_title = view.get("title", "")
        if v_path == view_path or v_title == view_path:
            target_view = view
            break

    if not target_view:
        return None

    # Return full view structure
    return {
        "type": target_view.get("type", "cards"),
        "title": target_view.get("title", ""),
        "max_columns": target_view.get("max_columns", 4),
        "sections": target_view.get("sections", []),
        "cards": target_view.get("cards", []),
    }


def enrich_card_with_state(card, states_dict):
    """Add state information to a card"""
    entity_id = card.get("entity")
    if not entity_id:
        return card

    # Find state for this entity
    state_data = states_dict.get(entity_id)
    if state_data:
        card["state"] = state_data.get("state")
        card["attributes"] = state_data.get("attributes", {})
        card["friendly_name"] = state_data["attributes"].get("friendly_name", entity_id)
    else:
        card["state"] = "unavailable"
        card["attributes"] = {}
        card["friendly_name"] = entity_id

    return card


@app.route("/dashboard/<path:dashboard_path>")
def dashboard(dashboard_path):
    # Get all states
    states = get_states()
    states_dict = {s["entity_id"]: s for s in states}

    # Variables for rendering
    dashboard_title = ""
    view_structure = None
    entities = []

    # Determine which type of dashboard to show
    if dashboard_path == "all":
        dashboard_title = "Wszystkie urządzenia"
        entity_ids = None
        entities = filter_entities(states, entity_ids)
    elif dashboard_path.startswith("area-"):
        area_id = dashboard_path[5:]  # Remove "area-" prefix
        dashboard_title = area_id
        entity_ids = get_entities_by_area(area_id)
        entities = filter_entities(states, entity_ids)
    elif dashboard_path.startswith("lovelace-"):
        # Parse lovelace path: "lovelace-dashboard_oscar-ada"
        lovelace_part = dashboard_path[9:]  # Remove "lovelace-" prefix

        # Split on first occurrence of dash after "dashboard_"
        if lovelace_part.startswith("dashboard_"):
            # Find the first "-" after "dashboard_"
            rest = lovelace_part[10:]  # Remove "dashboard_"
            dash_index = rest.find("-")

            if dash_index == -1:
                # No view path, just dashboard
                dashboard_id = lovelace_part
                view_path = ""
            else:
                # Split at the first "-"
                dashboard_id = "dashboard_" + rest[:dash_index]
                view_path = rest[dash_index+1:]
        else:
            # Fallback
            parts = lovelace_part.split("-", 1)
            dashboard_id = parts[0]
            view_path = parts[1] if len(parts) > 1 else ""

        dashboard_title = view_path if view_path else dashboard_id

        # Get full view structure
        view_structure = get_lovelace_view_structure(dashboard_id, view_path)

        if view_structure:
            # Enrich cards with state information
            for section in view_structure.get("sections", []):
                for card in section.get("cards", []):
                    enrich_card_with_state(card, states_dict)

            # Also enrich cards in view (for non-sections layout)
            for card in view_structure.get("cards", []):
                enrich_card_with_state(card, states_dict)
    else:
        # Unknown dashboard type
        dashboard_title = dashboard_path
        entities = []

    return render_template(
        "dashboard.html",
        entities=entities,
        view_structure=view_structure,
        dashboard_title=dashboard_title,
        dashboard_path=dashboard_path,
        last_update=datetime.now().strftime("%H:%M:%S"),
        auto_refresh=AUTO_REFRESH_INTERVAL,
        theme=THEME,
        grid_columns=GRID_COLUMNS,
        show_back_button=SHOW_BACK_BUTTON,
        show_last_update=SHOW_LAST_UPDATE,
    )


@app.route("/toggle/<path:dashboard_path>/<entity_id>")
def toggle(dashboard_path, entity_id):
    domain = entity_id.split(".")[0]

    try:
        call_service(domain, "toggle", entity_id)
    except Exception as e:
        print(f"Error toggling {entity_id}: {e}")

    return redirect(url_for("dashboard", dashboard_path=dashboard_path))


if __name__ == "__main__":
    app.run(
        host=os.getenv("FLASK_HOST", "0.0.0.0"),
        port=int(os.getenv("FLASK_PORT", 10010)),
        debug=os.getenv("FLASK_DEBUG", "True").lower() == "true"
    )
