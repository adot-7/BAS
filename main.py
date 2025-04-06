import os
import io
import uuid
import datetime
import time
from flask import (
    Flask, request, jsonify, abort, send_file, render_template)
import pandas as pd
from typing import List, Optional, Dict, Any, Tuple
from py3dbp import Packer, Bin, Item


# --- Flask App Setup ---
app = Flask(__name__)
# Optional: configure secret key if using sessions later
# app.secret_key = os.environ.get("FLASK_SECRET_KEY", "a_default_secret_key")
CONT_MAX_WEIGHT = 10000
# --- In-Memory State Simulation ---
# Simple demo state. Not constant across restarts
# Structure: {containerId: ContainerDefinitionDict}
defined_containers: Dict[str, Dict[str, Any]] = {}

zone_wise_containers: Dict[str, List] = {} #{'zone':[conta, contb, etc]}
items_ids_to_place: List = []
# Structure: {containerId: [PlacedItemDict, ...]}
# PlacedItemDict = {"itemId": str, "name": str, "position": {"start": (w,d,h), "end": (w,d,h)}, "props": ItemPropsDict}
current_stowage_state: Dict[str, List[Dict[str, Any]]] = {} #{'conta':[{'itemId': '01', etc}, etc]}

# Structure: {itemId: ItemPropertiesDict} - stores original props like dimensions, priority etc.
item_properties: Dict[str, Dict[str, Any]] = {}

# Structure: {"itemId": {"total_uses": int, "retrievals": [{"userId": str, "timestamp": str}, ...]}}
usage_log: Dict[str, Dict[str, Any]] = {}

# Structure: List of LogEntryDict
# LogEntryDict = {"logId": str, "timestamp": str, "userId": str, "actionType": str, "itemId": str, "details": {...}}
activity_log: List[Dict[str, Any]] = []

# --- Utility Functions ---
def add_log(actionType: str, itemId: str, details: Dict, userId: Optional[str] = "system"):
    """Adds an entry to the activity log."""
    log_entry = {
        "logId": str(uuid.uuid4()),
        "timestamp": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        "userId": userId or "unknown",
        "actionType": actionType,
        "itemId": itemId,
        "details": details,
    }
    activity_log.append(log_entry)
    print(f"LOG: {log_entry}") # Print log to console for debugging

def parse_iso_datetime(date_string: Optional[str]) -> Optional[datetime.datetime]:
    """Safely parses an ISO 8601 datetime string."""
    if not date_string:
        return None
    try:
        # Handle 'Z' for UTC timezone explicitly
        if date_string.endswith('Z'):
            date_string = date_string[:-1] + '+00:00'
        return datetime.datetime.fromisoformat(date_string)
    except ValueError:
        return None # Invalid format

def is_item_expired(item_id: str, current_time: datetime.datetime) -> bool:
    """Checks if an item is expired based on its properties."""
    props = item_properties.get(item_id)
    if not props or not props.get('expiryDate'):
        return False
    expiry_date = parse_iso_datetime(props['expiryDate'])
    return expiry_date is not None and expiry_date <= current_time

def is_item_depleted(item_id: str) -> bool:
    """Checks if an item has reached its usage limit."""
    props = item_properties.get(item_id)
    if not props or props.get('usageLimit') is None: # None means infinite or not applicable
        return False
    use_count = len(usage_log.get(item_id, {}).get("retrievals", []))
    return use_count >= props['usageLimit']

# --- Core Logic Functions (Placeholders - *** REPLACE WITH YOUR ALGORITHMS ***) ---

def calculate_placements() -> Dict:
    """
    ***Placement Algorithm (3D Bin Packing) using py3dbp***
    
    """
    print("Calculating Placements...")
    print(current_stowage_state)
    print(defined_containers)
    print(items_ids_to_place)
    placements = []
    rearrangements = []
    packer = Packer()
    preferred_zone_items_dict: Dict[str, List] = {} #{'zone': [itemid, item2id, etc]}
    for itemId in items_ids_to_place[:]:#global datatype defined above, making its copy cause shouldnt loop over it while removing items from it, fucks up the index
        preferred_zone = item_properties[itemId].get('preferredZone')
        if preferred_zone not in preferred_zone_items_dict:
            preferred_zone_items_dict[preferred_zone] = []
        preferred_zone_items_dict[preferred_zone].append(itemId)
        items_ids_to_place.remove(itemId)
    print(preferred_zone_items_dict)
    current = time.time()
    unplaced_items = 0
    placements: List[Dict[str, Any]] = []
    for zone, container_ids in zone_wise_containers.items():
        # Create bins for each container in the preferred zone
        for container_id in container_ids:
            container = defined_containers.get(container_id)
            if not container:
                continue
            packer.addBin(Bin(
                partno=container_id,
                WHD=(container.get('width'), container.get('height'), container.get('depth')),
                max_weight=CONT_MAX_WEIGHT,
                put_type=1
            ))
        items = 0

        # Add items to the packer for the current zone
        if preferred_zone_items_dict.get(zone) is None:
            continue
        for item_id in preferred_zone_items_dict.get(zone):
            item = item_properties.get(item_id)
            if not item:
                continue
            packer.addItem(Item(
                partno=item_id,
                name=item.get('name', 'unknown'),
                typeof='cube',
                WHD=(item['width'], item['height'], item['depth']),
                weight=item.get('mass', 0),
                level=100-int(item.get('priority', 0)),
                loadbear=100,  # Default load-bearing capacity
                updown=False,  # Allow flipping
                color='#0000E3')  # Default color
            )
            items+=1

        # Perform packing
        packer.pack(
            bigger_first=False,
            distribute_items=True,
            fix_point=True,
            check_stable=True,
            support_surface_ratio=0.750,
            number_of_decimals=0
        )

        print(f"Placed items in containers of Zone: {zone}, number of items placed in the Zone:{items}")

        
        # Collect placements from the packing results
        for box in packer.bins:
            print(":::::::::::", box.string())
            current_stowage_state[box.partno] = []
            print("FITTED ITEMS:")
            for item in box.items:
                start_pos = (item.position[0], item.position[1], item.position[2])
                end_pos = (item.position[0] + item.width, item.position[1] + item.height, item.position[2] + item.depth)
                position = {
                    "startCoordinates": {
                        "width": float(start_pos[0]),
                        "height": float(start_pos[1]),
                        "depth": float(start_pos[2])
                    },
                    "endCoordinates": {
                        "width": float(end_pos[0]),
                        "height": float(end_pos[1]),
                        "depth": float(end_pos[2])
                    }
                }
                item_to_add = {'itemId': item.partno,'name':item.name,'containerId': box.partno,'position':position}
                current_stowage_state[box.partno].append(item_to_add)
                print("partno : ",item.partno)
            unplaced_items+=len(packer.bins[-1].unfitted_items)
        
    end = time.time()
    print("Time taken to place the items: ", end-current)
    for key, value in current_stowage_state.items():
        print(f"Container ID: {key}")
        print(f"Total Items: {len(value)}")
    
    return end-current

def find_best_retrieval_option(search_key: str, search_type: str) -> Dict:
    """
    """
    print(f"Finding best retrieval for {search_type}: {search_key}")
    found_items_options = []
    for containerId, items_list_for_container in current_stowage_state.items():
        for item_dict in items_list_for_container:
            matches = False
            if search_type == 'itemId' and item_dict.get('itemId') == search_key:
                matches = True
            elif search_type == 'itemName' and item_dict.get('name') == search_key:
                matches = True
            if matches:
                found_items_options.append({
                    "item": {
                        "itemId": item_dict.get('itemId'),
                        "name": item_dict.get('name'),
                        "containerId": containerId,
                        "zone": defined_containers.get(containerId, {}).get('zone', 'Unknown'),
                        "position": item_dict.get('position', {})
                    },
                    "retrievalSteps": None,
                    "num_steps": None
                })

    if not found_items_options:
        return {"found": False, "item": None, "retrievalSteps": []}

    # Select the option with fewest steps
    best_option = min(found_items_options, key=lambda x: x['num_steps'])
    
    return {"found": True, "item": best_option["item"], "retrievalSteps": best_option["retrievalSteps"]}

def generate_return_plan(waste_items_to_return: List[Dict], undock_containerId: str, max_weight: float) -> Dict:
    """
    *** Placeholder for Return Planning Logic ***
    """
    return {}

def simulate_one_day(items_to_use: List[Dict], current_time: datetime.datetime) -> Tuple[Dict, datetime.datetime]:

    print(f"Simulating one day forward from {current_time}...")
    items_usable: List[Dict[str, Any]] = []
    for i in items_to_use:
        if i.get('itemId') in item_properties:
            item_prop = i.copy()
            item_prop['currentUsage'] = item_properties[i.get('itemId')].get('usageLimit')
            item_prop['expiryDate'] = item_properties[i.get('itemId')].get('expiryDate')
            items_usable.append(item_prop)
    print(items_usable)

    items_used_today = []
    items_newly_expired = []

    for item_dict in items_usable:
        usage_limit = item_properties[item_dict['itemId']].get('usageLimit')
        if usage_limit is not None:
            item_properties[item_dict['itemId']]['usageLimit'] = usage_limit - 1
        if is_item_depleted(item_dict['itemId']):
            items_used_today.append(item_dict['itemId'])
        if is_item_expired(item_dict['itemId'], current_time=current_time):
            items_newly_expired.append(item_dict['itemId'])
        
    # 2. Advance time
    new_time = current_time + datetime.timedelta(days=1)

    changes = {
        "itemsUsed": items_used_today,
        "itemsExpired": items_newly_expired,
    }
    return changes, new_time

# --- Global variable for simulation time ---
current_simulated_time = datetime.datetime.now()


# --- API Endpoints ---

# --- 1. Placement ---
@app.route("/api/placement", methods=['POST'])
def api_placement():
    """
    Calculates optimal placement for new items.
    """
    if not request.is_json:
        abort(400, description="Request must be JSON.")
    
    data = request.get_json()
    
    if data.get("items"):
        items_list = data.get("items") #Gives list of dict, with keys itemId, width, height,depth, priority, expiryDate, usageLimit, preferredZone
        for item in items_list:
            item_properties[item.get('itemId')] = item
            if item.get('itemId') not in items_ids_to_place:
                items_ids_to_place.append(item.get('itemId'))
            else:
                print(f"{item.get('itemId')}Already in the list to be placed")
    if data.get("containers"):
        containers_list = data.get("containers")
        container_dict={}
        for container in containers_list:
            try:
                if container.get('zone') not in zone_wise_containers: zone_wise_containers[container.get('zone')] = []
                zone_wise_containers[container.get('zone')].append(container["containerId"])
                defined_containers[container["containerId"]] = container #Adding the container to defined containers.
            except KeyError as e:
                print(f"Error: Missing key {e} in container data.")
    result = calculate_placements()

   
    placements = [items for items in current_stowage_state.values() if items]
    
    return jsonify({
        "success": True,
        "placements": placements,
        "Time Taken": f'{result} seconds'
    })

# --- 2. Search & Retrieval ---
@app.route("/api/search", methods=['GET'])
def api_search():
    item_id = request.args.get('itemId')
    item_name = request.args.get('itemName')

    if not item_id and not item_name:
        abort(400, description="Either itemId or itemName must be provided.")

    search_key = item_id if item_id else item_name
    search_type = 'itemId' if item_id else 'itemName'

    result = find_best_retrieval_option(search_key, search_type)

    return jsonify({
        "success": True,
        "found": result["found"],
        "item": result["item"],
        "retrievalSteps": result["retrievalSteps"]
    })

@app.route("/api/retrieve", methods=['POST'])
def api_retrieve():
    #Under working
    return jsonify({"success": False})


@app.route("/api/place", methods=['POST'])
def api_place():
    # Endpoint for astronaut MANUALLY placing an item somewhere, Under working
    return jsonify({"success": False})

# --- 3. Waste Management ---
@app.route("/api/waste/identify", methods=['GET'])
def api_waste_identify():
    #Under working
    return jsonify({
        "success": False,
        "wasteItems": None
    })

@app.route("/api/waste/return-plan", methods=['POST'])
def api_waste_return_plan():
    #Under working
    return jsonify({"success": False})

@app.route("/api/waste/complete-undocking", methods=['POST'])
def api_waste_complete_undocking():
    if not request.is_json: abort(400, description="Request must be JSON.")
    data = request.get_json()
    undocking_containerId = data.get('undockingContainerId')
    timestamp = data.get('timestamp')

    if not undocking_containerId:
        abort(400, description="Missing undockingContainerId.")
    items_removed_count = None
    #Under working
    return jsonify({"success": True, "itemsRemoved": items_removed_count})


# --- 4. Time Simulation ---
@app.route("/api/simulate/day", methods=['POST'])
def api_simulate_day():
    global current_simulated_time
    if not request.is_json: abort(400, description="Request must be JSON.")
    data = request.get_json()

    num_days = data.get('numOfDays')
    items_to_be_used = data.get('itemsToBeUsedPerDay', []) # List of {itemId/name} used each day

    if num_days is None or num_days < 1:
        num_days = 1

    total_changes = {"itemsUsed": [], "itemsExpired": []}

    for _ in range(num_days):
        changes_today, new_sim_time = simulate_one_day(items_to_be_used, current_simulated_time)
        current_simulated_time = new_sim_time # Update global time

        # Aggregate changes (simple list extend)
        total_changes["itemsUsed"].extend(changes_today["itemsUsed"])
        total_changes["itemsExpired"].extend(changes_today["itemsExpired"])
    # Add simulation log
    add_log("simulation", f"advance_{num_days}_days", {"newDate": current_simulated_time.isoformat()}, userId="system_simulation")

    return jsonify({
        "success": True,
        "newDate": current_simulated_time.isoformat(),
        "changes": total_changes
    })

# --- 5. Import/Export ---
@app.route("/api/import/containers", methods=['POST'])
def api_import_containers():
    files = list(request.files.values())
    file = files[0] if files else abort(400, description="No file part.")
    if file.filename == '':
        abort(400, description="No selected file.")
    if file and file.filename.endswith('.csv'):
        try:
            df = pd.read_csv(file)
            # --- Add column validation ---
            required_cols = ['zone','container_id', 'width_cm', 'depth_cm', 'height_cm']
            if not all(col in df.columns for col in required_cols):
                 abort(400, description=f"CSV missing required columns: {required_cols}")

            imported_count = 0
            errors = []
            global defined_containers
            # defined_containers.clear() # Clear existing? Or merge? Assuming merge/update.
            for index, row in df.iterrows():
                container_dict = row.to_dict()
                 # Add type conversion/validation if needed
                try:
                    container_dict['zone'] = str(container_dict.get('zone'))
                    container_dict['width'] = float(container_dict.pop('width_cm'))
                    container_dict['depth'] = float(container_dict.pop('depth_cm'))
                    container_dict['height'] = float(container_dict.pop('height_cm'))
                    container_dict['containerId'] = container_dict.pop('container_id')
                    defined_containers[container_dict['containerId']] = container_dict
                    print(defined_containers[container_dict['containerId']])
                    if container_dict.get('zone') not in zone_wise_containers: zone_wise_containers[container_dict.get('zone')] = []
                    zone_wise_containers[container_dict.get('zone')].append(container_dict['containerId'])

                    imported_count += 1
                except (ValueError, TypeError) as e:
                    errors.append({"row": index + 2, "message": f"Invalid numeric data: {e}"})
            print(defined_containers)


            add_log("import", "containers", {"count": imported_count, "errors": len(errors)}, userId="system_import")
            return jsonify({"success": True, "containersImported": imported_count, "errors": errors})
        except pd.errors.ParserError:
             abort(400, description="Error parsing CSV file.")
        except Exception as e:
             abort(500, description=f"An error occurred during import: {e}")
    else:
        abort(400, description="Invalid file type, only CSV allowed.")

@app.route("/api/import/items", methods=['POST'])
def api_import_items():
    # if 'itemsFile' not in request.files: abort(400, description="No file part.")
    files = list(request.files.values())
    file = files[0] if files else abort(400, description="No file part.")
    if file.filename == '': abort(400, description="No selected file.")
    if file and file.filename.endswith('.csv'):
        try:
            df = pd.read_csv(file)
             # --- Add column validation ---
            required_cols = ['itemId', 'name', 'width', 'depth', 'height', 'mass', 'priority']
            if not all(col in df.columns for col in required_cols):
                 abort(400, description=f"CSV missing required columns: {required_cols}")

            imported_count = 0
            errors = []
            global item_properties
            # item_properties.clear() # Clear or merge? Assuming merge/update.
            for index, row in df.iterrows():
                 item_dict = row.to_dict()
                 # Clean up potential NaN from optional fields read by pandas
                 item_dict = {k: (v if pd.notna(v) else None) for k, v in item_dict.items()}
                 # Add type conversion/validation
                 try:
                    item_dict['name'] = str(item_dict.get('name', 'Unknown'))
                    item_dict['width'] = float(item_dict.get('width', 0.0))
                    item_dict['depth'] = float(item_dict.get('depth', 0.0))
                    item_dict['height'] = float(item_dict.get('height', 0.0))
                    item_dict['mass'] = float(item_dict.get('mass', 0.0))
                    item_dict['priority'] = int(item_dict.get('priority', 0))
                    item_dict['preferredZone'] = str(item_dict.pop('preferred_zone', 'default_zone'))
                    # Optional fields
                    if item_dict.get('usageLimit') is not None: item_dict['usageLimit'] = int(item_dict['usageLimit'])
                    # Keep expiryDate as string for now, parse when needed
                    if item_dict.get('expiryDate') is not None: item_dict['expiryDate'] = parse_iso_datetime(item_dict['expiryDate'])

                    item_properties[item_dict['itemId']] = item_dict
                    items_ids_to_place.append(item_dict['itemId'])
                    imported_count += 1
                 except (ValueError, TypeError) as e:
                    errors.append({"row": index + 2, "message": f"Invalid numeric/integer data: {e}"})
                 print(index, row)

            print(item_properties)
            add_log("import", "items", {"count": imported_count, "errors": len(errors)}, userId="system_import")

            return jsonify({"success": True, "itemsImported": imported_count, "errors": errors})
        except pd.errors.ParserError:
             abort(400, description="Error parsing CSV file.")
        except Exception as e:
             abort(500, description=f"An error occurred during import: {e}")
    else:
        abort(400, description="Invalid file type, only CSV allowed.")


@app.route("/api/export/arrangement", methods=['GET'])
def api_export_arrangement():
    """Exports the current item layout as CSV."""
    data_to_export = []
    # Format: Item ID,Container ID,Coordinates (W1,D1,H1),(W2,D2,H2)
    for containerId, items in current_stowage_state.items():
        for item in items:
            pos = item.get("position", {})
            start = pos.get("startCoordinates", {})
            end = pos.get("endCoordinates", {})
            coord_str = f"({start.get('width',0)},{start.get('depth',0)},{start.get('height',0)}),({end.get('width',0)},{end.get('depth',0)},{end.get('height',0)})"
            data_to_export.append({
                "ItemID": item.get('itemId', 'N/A'),
                "ContainerID": containerId,
                "Coordinates": coord_str
            })

    if not data_to_export:
         # Return empty CSV? Or an error? Empty CSV seems better.
        df = pd.DataFrame(columns=["ItemID", "ContainerID", "Coordinates"])
    else:
        df = pd.DataFrame(data_to_export)

    # Use StringIO to avoid writing to disk
    output = io.StringIO()
    df.to_csv(output, index=False)
    output.seek(0)

    add_log("export", "arrangement", {"itemCount": len(df)}, userId="system_export")

    return send_file(
        io.BytesIO(output.getvalue().encode('utf-8')),
        mimetype='text/csv',
        as_attachment=True,
        download_name='current_arrangement.csv' # Corrected attribute
    )

# --- 6. Logging ---
@app.route("/api/logs", methods=['GET'])
def api_logs():
    start_date_str = request.args.get('startDate')
    end_date_str = request.args.get('endDate')
    item_id_filter = request.args.get('itemId')
    user_id_filter = request.args.get('userId')
    action_type_filter = request.args.get('actionType')

    start_date = parse_iso_datetime(start_date_str)
    end_date = parse_iso_datetime(end_date_str)

    if not start_date or not end_date:
        abort(400, description="Invalid or missing startDate or endDate (ISO format required).")

    filtered_logs = []
    for log in activity_log:
        log_time = parse_iso_datetime(log['timestamp'])
        if not log_time: continue # Skip invalid log entries

        # Apply filters
        time_match = start_date <= log_time <= end_date
        item_match = not item_id_filter or log.get('itemId') == item_id_filter
        user_match = not user_id_filter or log.get('userId') == user_id_filter
        action_match = not action_type_filter or log.get('actionType') == action_type_filter

        if time_match and item_match and user_match and action_match:
            filtered_logs.append(log)

    # Sort logs? Chronologically is likely default.
    return jsonify({"logs": filtered_logs})


# --- 7. Functional UI Route ---
@app.route("/")
def index():
    """Serves the main HTML page."""
    return render_template("index.html")

# --- Flask App Execution ---
if __name__ == '__main__':
    #Run on 0.0.0.0 to be accessible within Docker network
    # Use debug=True only for development, set it to False for production/evaluation scenarios
    app.run(host='0.0.0.0', port=8000, debug=True)