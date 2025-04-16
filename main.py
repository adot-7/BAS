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
from werkzeug.exceptions import HTTPException


# --- Flask App Setup ---
app = Flask(__name__)
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
current_item_state: Dict[str, Dict[str, Any]] = {}#{'id':{'itemid':'id', 'position':position, 'containerId':'contid'}}
# Structure: {itemId: ItemPropertiesDict} - stores original props like dimensions, priority etc.
item_properties: Dict[str, Dict[str, Any]] = {}

empty_container_ids = [] #for undocking and second placement 

# #We need a list of container IDs for keeping track of containers which have been packed(partially or fully) with items, so that if more items arrive in shipment, only those containers not in this list are considered?
# filled_container_ids = [] #['conta', 'contb', etc.]
# Structure: {"itemId": {"total_uses": int, "retrievals": [{"userId": str, "timestamp": str}, ...]}} #here total uses is len(retrievals)?
usage_log: Dict[str, Dict[str, Any]] = {}

# Structure: List of LogEntryDict
# LogEntryDict = {"logId": str, "timestamp": str, "userId": str, "actionType": str, "itemId": str, "details": {...}}
activity_log: List[Dict[str, Any]] = []

#For keeping track of depleted and expired items and not having to run iterations everytime api/waste/identify is hit
waste_items: List[Dict[str, Any]] = [] #[{"itemId": 01, "reason": "expired", etc}, etc]
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
    date_string = str(date_string)
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
    if not props or not props.get('expiry_date'):
        return False
    expiry_date = parse_iso_datetime(props['expiry_date'])
    return expiry_date is not None and expiry_date <= current_time

def is_item_depleted(item_id: str) -> bool:
    """Checks if an item has reached its usage limit."""
    props = item_properties.get(item_id)
    if not props or props.get('usage_limit') is None: # None means infinite or not applicable
        return False
    use_count = len(usage_log.get(item_id, {}).get("retrievals", []))
    return use_count >= props['usage_limit']

# --- Core Logic Functions (Placeholders - *** REPLACE WITH YOUR ALGORITHMS ***) ---

def calculate_placements() -> Dict:
    """
    ***Placement Algorithm (3D Bin Packing) using py3dbp(modified)***
    
    """
    global current_stowage_state
    global items_ids_to_place
    global current_item_state
    global usage_log
    # global filled_container_ids
    print("Calculating Placements...")
    # print(current_stowage_state)
    # print(defined_containers)
    # print(items_ids_to_place)
    
    preferred_zone_items_dict: Dict[str, List] = {} #{'zone': [itemid, item2id, etc]}
    for itemId in items_ids_to_place[:]:#global datatype defined above, making its copy cause shouldnt loop over it while removing items from it, fucks up the index
        preferred_zone = item_properties[itemId].get('preferredZone')
        if preferred_zone not in preferred_zone_items_dict:
            preferred_zone_items_dict[preferred_zone] = []
        preferred_zone_items_dict[preferred_zone].append(itemId)
    items_ids_to_place.clear()
    total=0
    unplaced_items_ids = []
    global empty_container_ids
    current = time.time()
    '''
    This section handles first placement in preferred zones
    '''
    for zone, container_ids in zone_wise_containers.items():
        packer = Packer()
        # Create bins for each container in the preferred zone
        for container_id in container_ids:
            #check if previosuly filled
            if len(current_stowage_state.get(container_id, []))>0:
                continue
            container = defined_containers.get(container_id)
            if not container:
                continue
            packer.addBin(Bin(
                partno=container_id,
                WHD=(container.get('width'), container.get('height'), container.get('depth')),
                max_weight=CONT_MAX_WEIGHT,
                put_type=1
            ))

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
                updown=True,  # Allow flipping, otherwise problem in placing some items(like item ID 172 in sample)
                color='#0000E3')  # Default color
            )

        # Perform packing
        packer.pack(
            bigger_first=False,
            distribute_items=True,
            fix_point=False,
            check_stable=False,
            support_surface_ratio=0.750,
            number_of_decimals=0
        )
        
        # Collect placements from the packing results
        if packer.bins:
            last_box = packer.bins[-1]
        else:
            print("No bins available in packer.")
        for box in packer.bins:
            current_stowage_state[box.partno] = [] #First make sure the key as the contianer id is always added, doesnt matter if number of items 0 or sum else
            if len(box.items) == 0:
                empty_container_ids.append(box.partno)
                # print(f"ID:{box.partno} Added to possible container IDs")
            # print(":::::::::::", box.string())
            # print("FITTED ITEMS:")
            for item in box.items:
                start_pos = (item.position[0], item.position[1], item.position[2])
                new_WHD = item.getDimension() #[W, H, D] of the rotated item, as it will depend on the rotation type of the item placed. 
                end_pos = (item.position[0] + new_WHD[0], item.position[1] + new_WHD[1], item.position[2] + new_WHD[2])
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
                current_item_state[item.partno] = item_to_add
                usage_log[item.partno] = {"total_uses": 0, "retrievals":[]}
                # print("partno : ",item.partno)
                total+=1
            if box == last_box:
                for unplaced_item in box.unfitted_items:
                    unplaced_items_ids.append(unplaced_item.partno)
                    
    '''
    This section will handle the unplaced items, will place them in any container with number of fitted items = 0
    '''
    print("Placing unplaced items in empty containers...")
    # print("Possible Container Ids: ", possible_container_ids)
    # print("Number of Unplaced items' Ids: ", len(unplaced_items_ids))
    packer = Packer()
    for container_id in empty_container_ids:
        container = defined_containers.get(container_id)
        if not container:
            continue
        packer.addBin(Bin(
            partno=container_id,
            WHD=(container.get('width'), container.get('height'), container.get('depth')),
            max_weight=CONT_MAX_WEIGHT,
            put_type=1
        ))
    empty_container_ids.clear()
    for item_id in unplaced_items_ids:
        item = item_properties.get(int(item_id))
        if not item:
            continue
        packer.addItem(Item(
            partno=item_id,
            name=item.get('name', 'unknown'),
            typeof='cube',
            WHD=(item['width'], item['height'], item['depth']),
            weight=item.get('mass', 0),
            level=100-int(item.get('priority', 0)),
            loadbear=100,  
            updown=True,  # Allow flipping, otherwise problem in placing some items(like item ID 172 in sample)
            color='#0000E3')  
            )
    packer.pack(
            bigger_first=False,
            distribute_items=True,
            fix_point=False,
            check_stable=False,
            support_surface_ratio=0.750,
            number_of_decimals=0
        )
    if packer.bins:
        last_box = packer.bins[-1]
    for box in packer.bins:
        # print(":::::::::::", box.string())
        # print("FITTED ITEMS:")
        if len(box.items)==0:
            empty_container_ids.append(box.partno)
        for item in box.items:
            start_pos = (item.position[0], item.position[1], item.position[2])
            new_WHD = item.getDimension() #[W, H, D] of the rotated item, as it will depend on the rotation type of the item placed. 
            end_pos = (item.position[0] + new_WHD[0], item.position[1] + new_WHD[1], item.position[2] + new_WHD[2])
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
            current_item_state[item.partno] = item_to_add
            usage_log[item.partno] = {"total_uses": 0, "retrievals":[]}

            # print("partno : ",item.partno)
            total+=1
        if box == last_box:
            print("UNPLACED ITEM IDS")
            for unfitted_item in box.unfitted_items:
                print(unfitted_item.partno)
            print("********************")
    
    end = time.time()
    
    # for key, value in current_stowage_state.items():
    #     print(f"Container ID: {key}")
    #     print(f"Total Items: {len(value)}")
    print("EMPTY CONTAINER IDS:")
    print(empty_container_ids)
    print("*********************")
    print("Time taken to place the items: ", end-current)
    print(f"Total items placed: {total}\n")
    
    return end-current

def find_best_retrieval_option(search_key: str, search_type: str) -> Dict:
    """
    """
    print(f"Finding best retrieval for {search_type}: {search_key}")
    found_items_options = []
    for containerId, items_list_for_container in current_stowage_state.items():
        for item_dict in items_list_for_container:
            matches = False
            if (search_type == 'itemId') and int(item_dict.get('itemId')) == int(search_key):
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
                    "startCoordinates": item_dict.get('position', {}).get('startCoordinates', {})
                })

    if not found_items_options:
        return {"found": False, "item": None, "retrievalSteps": []}

    # Select the option with minimum startCoordinates (based on width, height, depth)
    best_option = min(
        found_items_options,
        key=lambda x: (
            x['startCoordinates'].get('width', float('inf')),
            x['startCoordinates'].get('height', float('inf')),
            x['startCoordinates'].get('depth', float('inf'))
        )
    )
    item_ids_to_set_aside = []
    pos_list = []
    target_item_dict = best_option['item']
    target_item_cont_id = target_item_dict['containerId']
    target_item_width_min:float = target_item_dict['position']['startCoordinates']['width']
    target_item_depth_min:float = target_item_dict['position']['startCoordinates']['depth']
    target_item_height_min:float = target_item_dict['position']['startCoordinates']['height']
    target_item_width_max:float = target_item_dict['position']['endCoordinates']['width']
    target_item_depth_max:float = target_item_dict['position']['endCoordinates']['depth']
    for itemDict in current_stowage_state[target_item_cont_id]:
        current_item_height_max:float = itemDict['position']['endCoordinates']['height']
        if  current_item_height_max <= target_item_height_min: #THis will result in a 2D rectangle intersection case.
            current_item_width_min:float = itemDict['position']['startCoordinates']['width']
            current_item_depth_min:float = itemDict['position']['startCoordinates']['depth']
            current_item_width_max:float = itemDict['position']['endCoordinates']['width']
            current_item_depth_max:float = itemDict['position']['endCoordinates']['depth']
            #Bad logic, but keeping as a sign of learning
            # #First possibility is current item coords(width, depth) are starting between target item coords
            # if (target_item_width_min<=current_item_width_min<=target_item_width_max) and (target_item_depth_min<=current_item_depth_min<=target_item_depth_max):
            #     item_ids_to_set_aside.append(item_dict['itemId'])
            # #Second possibility is current item coords(width, depth) are ending between target item coords
            # elif (target_item_width_min<=current_item_width_max<=target_item_width_max) and (target_item_depth_min<=current_item_depth_max<=target_item_depth_max):
            #     item_ids_to_set_aside.append(item_dict['itemId'])
            # #Current item coords(width, depth) both within target item coords will be covered by either of above condition
            # #Finally, the last possibility is that target item width coords in between current item width coords  
            
            #Good logic
            #Here we think of the current item now as rectangle with bounds (width_min, depth_min) to (width_max, depth_max) AND the target item as a rectangle similarly
            #Now, it becomes easy to check for their intersections.
            if (current_item_width_min>=target_item_width_max) or (current_item_width_max<=target_item_width_min) or (current_item_depth_max<=target_item_depth_min) or (current_item_depth_min>=target_item_depth_max):
                #Means the item rect(width, depth) is not intersecting with target item (width, depth)
                pass
            else:
                item_ids_to_set_aside.append(itemDict['itemId'])
                pos_list.append(itemDict['position'])
    retrieval_steps = []
    step = 0
    for i, item_id in enumerate(item_ids_to_set_aside):
        step = i+1
        action = "setAside then placeBack"
        itemName = item_properties[item_id]['name']
        position = pos_list[i]
        retrieval_steps.append({"step":step, "action":action, "itemId":item_id, "itemName":itemName, "position":position})
    retrieval_steps.append({"step":step+1, "action":"retrieve", "itemId":target_item_dict['itemId'], "ItemName":target_item_dict['name']})


    
    return {"found": True, "item": best_option["item"], "retrievalSteps": retrieval_steps}

def generate_return_plan(waste_items_to_return: List[Dict], undock_containerId: str, max_weight: float) -> Dict:
    """
    *** Placeholder for Return Planning Logic ***
    """
    return {}

def simulate_one_day(items_to_use: List, current_time: datetime.datetime) -> Tuple[Dict, datetime.datetime]:

    print(f"Simulating one day forward from {current_time}...")
    items_usable: List[Dict[str, Any]] = []
    items_to_use = [int(i) for i in items_to_use]
    for i in items_to_use:
        if i in item_properties.keys():
            item_prop = {}
            item_prop['itemId'] = i
            item_prop['currentUsage'] = item_properties[i].get('usage_limit')
            item_prop['expiry_date'] = item_properties[i].get('expiry_date') 
            items_usable.append(item_prop)
    # print(items_usable)

    items_used = []
    items_expired = []

    for item_dict in items_usable:
        usage_limit = item_properties[item_dict['itemId']].get('usage_limit')
        if usage_limit is not None:
            if is_item_depleted(item_dict['itemId']):
                items_used.append(item_dict['itemId'])            
            if is_item_expired(item_dict['itemId'], current_time=current_time):
                items_expired.append(item_dict['itemId'])
            else:
                item_properties[item_dict['itemId']]['usage_limit'] = usage_limit - 1
        
    # 2. Advance time
    new_time = current_time + datetime.timedelta(days=1)

    changes = {
        "itemsUsed": items_used,
        "itemsExpired": items_expired,
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
    global item_properties
    global items_ids_to_place
    global zone_wise_containers
    global defined_containers

    if not request.is_json:
        abort(400, description="Request must be JSON.")
    
    data = request.get_json()
    
    if data.get("items"):
        items_list = data.get("items") #Gives list of dict, with keys itemId, width, height,depth, priority, expiry_date, usage_limit, preferredZone
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
    # print(items_ids_to_place)
    # print(item_properties)
    # print(zone_wise_containers)
    # print(defined_containers)
    result = calculate_placements()

   
    placements = [item for items in current_stowage_state.values() for item in items]
    add_log("placement", "container_placement", {"Total_items": len(placements), "Total_containers": len(current_stowage_state.keys())}, userId="system_placement")
    return jsonify({
        "success": True,
        "placements": placements,
        "Time_Taken": f'{result} seconds'
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
    add_log("search", search_key, {"type": search_type}, userId="system_search")
    return jsonify({
        "success": True,
        "found": result["found"],
        "item": result["item"],
        "retrievalSteps": result["retrievalSteps"]
    })

@app.route("/api/retrieve", methods=['POST'])
def api_retrieve():
    global usage_log
    global waste_items
    global item_properties
    if not request.is_json:
        abort(400, description="Request must be JSON.")  
    data = request.get_json()

    itemId_to_retrieve = int(data.get("itemId"))
    if not itemId_to_retrieve:
        abort(400, description="JSON missing Item ID.")
    if not usage_log.get(itemId_to_retrieve):
        abort(400, description="Item doesn't exist in the system.")
    if is_item_depleted(itemId_to_retrieve):
        abort(400, description="Item usage limit reached. Cannot be retrieved.")
    userId = data.get("userId", "userId")
    timestamp = data.get("timestamp", current_simulated_time.isoformat())
    retrieval_log_entry = {"userId": userId, "timestamp": timestamp}
    add_log("retrieve", itemId_to_retrieve, retrieval_log_entry, userId="system_retrieve")
    usage_log[itemId_to_retrieve]["total_uses"] += 1
    usage_log[itemId_to_retrieve]["retrievals"].append(retrieval_log_entry)
    item_properties[itemId_to_retrieve]["usage_limit"] -= 1 #Reducing usage Limit
    if is_item_depleted(itemId_to_retrieve):
        #Updating waste item List
        waste_item_to_add = current_item_state.get(itemId_to_retrieve)
        waste_item_to_add["reason"] = "Out of Uses"
        if waste_item_to_add not in waste_items:    
            waste_items.append(waste_item_to_add)
    return jsonify({"success": True})


@app.route("/api/place", methods=['POST'])
def api_place():
    # Endpoint for astronaut MANUALLY placing an item somewhere, Under working

    return jsonify({"success": False})

# --- 3. Waste Management ---
@app.route("/api/waste/identify", methods=['GET'])
def api_waste_identify():
    return jsonify({
        "success": True,
        "wasteItems": waste_items
    })

@app.route("/api/waste/return-plan", methods=['POST'])
def api_waste_return_plan():
    if not request.is_json:
        abort(400, description="Request must be JSON.")  
    data = request.get_json()
    required_keys = ["undockingContainerId", 'undockingDate', 'maxWeight']
    missing_keys = [key for key in required_keys if key not in data]
    if missing_keys:
        abort(400, description=f"Missing required keys: {', '.join(missing_keys)}")
    undockingContainerId = data['undockingContainerId']
    undockingDate = data['undockingDate']
    maxWeight = data['maxWeight']
    if maxWeight<=0:
        abort(400, description="Maximum Mass must be greater than 0.")
    if undockingContainerId not in current_stowage_state:
        abort(400, description="Container ID not found in current stowage state.")
    volume_t = 0
    mass=0
    returnPlan: List[Dict[str, Any]] = []
    finalRetrievalSteps: List[Dict[str, Any]] = []
    return_items: List[Dict[str, Any]] = []
    #Have to place the waste items in the container
    packer = Packer()
    packer.addBin(Bin(
        partno=undockingContainerId,
        WHD=(defined_containers[undockingContainerId]['width'], defined_containers[undockingContainerId]['height'], defined_containers[undockingContainerId]['depth']),
        max_weight=maxWeight,
        put_type=1
    ))
    for wasteItemDict in waste_items:
        itemProp = item_properties.get(int(wasteItemDict['itemId']))
        if not itemProp:
            continue
        packer.addItem(Item(
            partno=wasteItemDict['itemId'],
            name = wasteItemDict['name'],
            typeof='cube',
            WHD = (itemProp['width'], itemProp['height'], itemProp['depth']),
            weight = itemProp.get('mass', 0),
            level=0,
            loadbear=100,
            updown=True,
            color='#0000E3'
        ))
    packer.pack(
        bigger_first=False,
        distribute_items=True,
        fix_point=False,
        check_stable=False,
        support_surface_ratio=0.750,
        number_of_decimals=0
    )
    step=1
    for i, item in enumerate(current_stowage_state[undockingContainerId]):
        step+=i
        returnPlan.append({
            "step":step,
            "itemId":item['itemId'],
            "itemName":item['name'],
            "fromContainer":undockingContainerId,
            "toContainer":empty_container_ids[0]
        })
    step+=1
    for i, item in enumerate(packer.bins[0].items):
        step+=i
        returnPlan.append({
            "step":step,
            "itemId":item.partno,
            "itemName":item.name,
            "fromContainer":current_item_state.get(int(item.partno))['containerId'],
            "toContainer":undockingContainerId
        })
        volume_t += float(item.width) * float(item.height) * float(item.depth)
        mass+=item.weight
        result_retrieval = find_best_retrieval_option(search_key=item.partno, search_type='itemId')
        retrieval_steps = result_retrieval["retrievalSteps"]
        finalRetrievalSteps.append(retrieval_steps)
        reason=None
        for i in waste_items:
            if i['itemId']==item.partno:
                reason = i['reason']
        return_items.append({
            "itemId":item.partno,
            "name": item.name,
            "reason": reason
        })
    returnPlan = sorted(returnPlan, key=lambda x: x['step'])
    returnManifest: Dict[str, Any] = {
    "undockingContainerId":undockingContainerId,
    "undockingDate":undockingDate,
    "returnItems":return_items,
    "totalVolume":volume_t,
    "totalWeight":mass
    }
    return jsonify({
        "success":True,
        "returnPlan":returnPlan,
        "retrievalSteps":finalRetrievalSteps,
        "returnManifest":returnManifest
    })

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
    global waste_items
    if not request.is_json: abort(400, description="Request must be JSON.")
    data = request.get_json()

    num_days = data.get('numOfDays')
    items_to_be_used = data.get('itemsToBeUsedPerDay', []) # List of itemId used each day
    print(num_days) #int
    print(items_to_be_used) #list of str ids 
    if num_days is None or num_days < 1:
        num_days = 1

    total_changes = {"itemsUsed": [], "itemsExpired": []}

    for _ in range(num_days):
        changes_today, new_sim_time = simulate_one_day(items_to_be_used, current_simulated_time)
        current_simulated_time = new_sim_time # Update global time

        # Aggregate changes (simple list extend)
        total_changes["itemsUsed"].extend(
            item for item in changes_today["itemsUsed"] if item not in total_changes["itemsUsed"]
        )
        total_changes["itemsExpired"].extend(
            item for item in changes_today["itemsExpired"] if item not in total_changes["itemsExpired"]
        )

    for item_used_id in total_changes['itemsUsed']:
        waste_item_to_add = current_item_state.get(item_used_id)
        waste_item_to_add["reason"] = "Out of Uses"
        if waste_item_to_add in waste_items:
            continue
        waste_items.append(waste_item_to_add)
    for item_used_id in total_changes['itemsExpired']:
        waste_item_to_add = current_item_state.get(item_used_id)
        waste_item_to_add["reason"] = "Expired"
        if waste_item_to_add in waste_items:
            continue
        waste_items.append(waste_item_to_add)
    print(waste_items)
    
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
    global zone_wise_containers
    global defined_containers
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
            for index, row in df.iterrows():
                container_dict = row.to_dict()
                 # Add type conversion/validation if needed
                try:
                    container_dict['zone'] = str(container_dict.get('zone'))
                    container_dict['width'] = float(container_dict.pop('width_cm'))
                    container_dict['depth'] = float(container_dict.pop('depth_cm'))
                    container_dict['height'] = float(container_dict.pop('height_cm'))
                    container_dict['containerId'] = container_dict.pop('container_id')
                    if defined_containers.get(container_dict['containerId']):
                        print("Container ID already exists. Skipping.")
                        continue
                    defined_containers[container_dict['containerId']] = container_dict
                    # print(defined_containers[container_dict['containerId']])
                    if container_dict.get('zone') not in zone_wise_containers: zone_wise_containers[container_dict.get('zone')] = []
                    zone_wise_containers[container_dict.get('zone')].append(container_dict['containerId'])

                    imported_count += 1
                except (ValueError, TypeError) as e:
                    errors.append({"row": index + 2, "message": f"Invalid numeric data: {e}"})
            # print(defined_containers)


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
    global item_properties
    global items_ids_to_place
    
    # if 'itemsFile' not in request.files: abort(400, description="No file part.")
    files = list(request.files.values())
    file = files[0] if files else abort(400, description="No file part.")
    if file.filename == '': abort(400, description="No selected file.")
    if file and file.filename.endswith('.csv'):
        try:
            df = pd.read_csv(file)
            # --- Add column validation ---
            required_cols = ['itemId', 'name', 'width', 'depth', 'height', 'mass', 'priority']
            alternative_cols = ['item_id', 'name', 'width_cm', 'depth_cm', 'height_cm', 'mass_kg', 'priority']
            
            if not all(col in df.columns for col in required_cols) and not all(col in df.columns for col in alternative_cols):
                abort(400, description=f"CSV missing required columns: {required_cols} or {alternative_cols}")

            # Normalize column names if alternative columns are used
            if all(col in df.columns for col in alternative_cols):
                df.rename(columns={
                    'item_id': 'itemId',
                    'width_cm': 'width',
                    'depth_cm': 'depth',
                    'height_cm': 'height',
                    'mass_kg': 'mass'
                }, inplace=True)

            imported_count = 0
            errors = []
            for index, row in df.iterrows():
                item_dict = row.to_dict()
                # Clean up potential NaN from optional fields read by pandas
                item_dict = {k: (v if pd.notna(v) else None) for k, v in item_dict.items()}
                # Add type conversion/validation
                try:
                    if item_properties.get(item_dict['itemId']):
                        print("Item Id already exists. Skipping.")
                        continue
                    item_dict['name'] = str(item_dict.get('name', 'Unknown'))
                    item_dict['width'] = float(item_dict.get('width', 0.0))
                    item_dict['depth'] = float(item_dict.get('depth', 0.0))
                    item_dict['height'] = float(item_dict.get('height', 0.0))
                    item_dict['mass'] = float(item_dict.get('mass', 0.0))
                    item_dict['priority'] = int(item_dict.get('priority', 0))
                    item_dict['preferredZone'] = str(item_dict.pop('preferred_zone', 'default_zone'))
                    # Optional fields
                    if item_dict.get('usage_limit') is not None: item_dict['usage_limit'] = int(item_dict['usage_limit'])
                    # Keep expiry_date as string for now, parse when needed
                    if item_dict.get('expiry_date') is not None: item_dict['expiry_date'] = parse_iso_datetime(item_dict['expiry_date'])  
                    item_properties[item_dict['itemId']] = item_dict
                    items_ids_to_place.append(item_dict['itemId'])
                    imported_count += 1
                except (ValueError, TypeError) as e:
                    errors.append({"row": index + 2, "message": f"Invalid numeric/integer data: {e}"})
                # print(index, row)

            # print(item_properties)
            add_log("import", "items", {"count": imported_count, "errors": len(errors)}, userId="system_import")
            print("Total Items Imported: ", imported_count)
            print("Total Items: ", len(item_properties))
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

    start_date = parse_iso_datetime(start_date_str) or datetime.datetime.min.replace(tzinfo=datetime.timezone.utc)
    end_date = parse_iso_datetime(end_date_str) or datetime.datetime.max.replace(tzinfo=datetime.timezone.utc)
    print(start_date)
    print(end_date)
    filtered_logs = []
    print(activity_log)
    for log in activity_log:
        log_time = parse_iso_datetime(log['timestamp'])
        if not log_time:continue # Skip invalid log entries

        # Apply filters
        # Ensure all datetime objects are naive for comparison
        log_time_naive = log_time.replace(tzinfo=None) if log_time else None
        start_date_naive = start_date.replace(tzinfo=None)
        end_date_naive = end_date.replace(tzinfo=None)

        time_match = start_date_naive <= log_time_naive <= end_date_naive
        item_match = not item_id_filter or log.get('itemId') == item_id_filter
        user_match = not user_id_filter or log.get('userId') == user_id_filter
        action_match = not action_type_filter or log.get('actionType') == action_type_filter
        print(time_match, item_match, user_match, action_match)
        if time_match and item_match and user_match and action_match:
            filtered_logs.append(log)

    # Sort logs? Chronologically is likely default.
    return jsonify({"success":True, "logs": filtered_logs})


# --- 7. Functional UI Route ---
@app.route("/")
def index():
    """Serves the main HTML page."""
    return render_template("index.html")

@app.errorhandler(Exception)
def handle_exception(e):
    # Handle HTTP exceptions (e.g., 404, 500)
    if isinstance(e, HTTPException):
        response = jsonify({
            "success": False,
            "description": e.description
        })
        response.status_code = e.code
        return response

    # Handle non-HTTP exceptions
    response = jsonify({
        "success": False,
        "description": "An unexpected error occurred."
    })
    response.status_code = 500
    return response

# --- Flask App Execution ---
if __name__ == '__main__':
    #Run on 0.0.0.0 to be accessible within Docker network
    app.run(host='0.0.0.0', port=8000, debug=True)