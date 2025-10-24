from flask import Blueprint, request, jsonify
from datetime import datetime, timedelta
from bson import ObjectId

def init_inventory_blueprint(mongo, token_required, serialize_doc):
    """Initialize the inventory blueprint with database and auth decorator"""
    inventory_bp = Blueprint('inventory', __name__, url_prefix='/inventory')

    def update_item_stock(item_id, user_id):
        """Update item stock based on movements"""
        try:
            # Get all movements for this item
            movements = list(mongo.db.inventory_movements.find({
                'itemId': item_id,
                'userId': user_id
            }).sort('movementDate', 1))
            
            current_stock = 0
            for movement in movements:
                if movement['movementType'] in ['in', 'adjustment']:
                    current_stock += movement['quantity']
                elif movement['movementType'] in ['out']:
                    current_stock -= abs(movement['quantity'])
            
            # Update item stock
            item = mongo.db.inventory_items.find_one({'_id': item_id})
            if not item:
                return False
            
            # Determine status based on stock level
            status = 'active'
            if current_stock <= 0:
                status = 'out_of_stock'
            elif current_stock <= item.get('minimumStock', 0):
                status = 'low_stock'
            
            mongo.db.inventory_items.update_one(
                {'_id': item_id},
                {
                    '$set': {
                        'currentStock': current_stock,
                        'status': status,
                        'updatedAt': datetime.utcnow()
                    }
                }
            )
            
            return True
            
        except Exception as e:
            print(f"Error updating item stock: {str(e)}")
            return False

    def create_cogs_expense(item_id, quantity_sold, user_id):
        """Create COGS expense when inventory is sold"""
        try:
            # Get item details
            item = mongo.db.inventory_items.find_one({'_id': item_id})
            if not item:
                return False
            
            # Calculate COGS
            cogs_amount = item['costPrice'] * quantity_sold
            
            # Create expense record for COGS
            expense_data = {
                '_id': ObjectId(),
                'userId': user_id,
                'amount': cogs_amount,
                'title': f"COGS - {item['itemName']}",
                'description': f"Cost of Goods Sold for {quantity_sold} units of {item['itemName']}",
                'category': 'Cost of Goods Sold',
                'date': datetime.utcnow(),
                'tags': ['COGS', 'Inventory', 'Auto-generated'],
                'paymentMethod': 'inventory',
                'notes': f"Auto-generated COGS expense for inventory sale. Item: {item['itemName']}, Quantity: {quantity_sold}, Unit Cost: {item['costPrice']}",
                'createdAt': datetime.utcnow(),
                'updatedAt': datetime.utcnow()
            }
            
            mongo.db.expenses.insert_one(expense_data)
            return True
            
        except Exception as e:
            print(f"Error creating COGS expense: {str(e)}")
            return False

    # ==================== ITEM MANAGEMENT ENDPOINTS ====================

    @inventory_bp.route('/items', methods=['POST'])
    @token_required
    def add_item(current_user):
        """Add a new inventory item"""
        try:
            data = request.get_json()
            
            # Validate required fields
            required_fields = ['itemName', 'category', 'costPrice', 'sellingPrice', 'unit']
            for field in required_fields:
                if not data.get(field):
                    return jsonify({
                        'success': False,
                        'message': f'{field} is required',
                        'errors': {field: [f'{field} is required']}
                    }), 400
            
            # Check if item already exists
            existing_item = mongo.db.inventory_items.find_one({
                'userId': current_user['_id'],
                'itemName': data['itemName']
            })
            
            if existing_item:
                return jsonify({
                    'success': False,
                    'message': 'Item with this name already exists',
                    'errors': {'itemName': ['Item already exists']}
                }), 400
            
            # Validate numeric fields
            try:
                cost_price = float(data['costPrice'])
                selling_price = float(data['sellingPrice'])
                if cost_price < 0 or selling_price < 0:
                    return jsonify({
                        'success': False,
                        'message': 'Prices must be non-negative',
                        'errors': {'price': ['Prices must be non-negative']}
                    }), 400
            except (ValueError, TypeError):
                return jsonify({
                    'success': False,
                    'message': 'Invalid price format',
                    'errors': {'price': ['Prices must be valid numbers']}
                }), 400
            
            # Validate stock levels
            current_stock = int(data.get('currentStock', 0))
            minimum_stock = int(data.get('minimumStock', 0))
            maximum_stock = int(data.get('maximumStock', 0)) if data.get('maximumStock') else None
            
            if current_stock < 0 or minimum_stock < 0:
                return jsonify({
                    'success': False,
                    'message': 'Stock levels must be non-negative',
                    'errors': {'stock': ['Stock levels must be non-negative']}
                }), 400
            
            # Determine initial status
            status = 'active'
            if current_stock <= 0:
                status = 'out_of_stock'
            elif current_stock <= minimum_stock:
                status = 'low_stock'
            
            # Create item record
            item_data = {
                '_id': ObjectId(),
                'userId': current_user['_id'],
                'itemName': data['itemName'].strip(),
                'itemCode': data.get('itemCode', '').strip() or None,
                'description': data.get('description', '').strip() or None,
                'category': data['category'].strip(),
                'costPrice': cost_price,
                'sellingPrice': selling_price,
                'currentStock': current_stock,
                'minimumStock': minimum_stock,
                'maximumStock': maximum_stock,
                'unit': data['unit'].strip(),
                'supplier': data.get('supplier', '').strip() or None,
                'location': data.get('location', '').strip() or None,
                'status': status,
                'lastRestocked': datetime.utcnow() if current_stock > 0 else None,
                'expiryDate': None,
                'tags': data.get('tags', []) if isinstance(data.get('tags'), list) else [],
                'images': data.get('images', []) if isinstance(data.get('images'), list) else [],
                'notes': data.get('notes', '').strip() or None,
                'createdAt': datetime.utcnow(),
                'updatedAt': datetime.utcnow()
            }
            
            result = mongo.db.inventory_items.insert_one(item_data)
            
            # Create initial stock movement if stock > 0
            if current_stock > 0:
                movement_data = {
                    '_id': ObjectId(),
                    'userId': current_user['_id'],
                    'itemId': result.inserted_id,
                    'movementType': 'in',
                    'quantity': current_stock,
                    'unitCost': cost_price,
                    'totalCost': cost_price * current_stock,
                    'reason': 'initial_stock',
                    'reference': 'Initial Stock Entry',
                    'stockBefore': 0,
                    'stockAfter': current_stock,
                    'movementDate': datetime.utcnow(),
                    'notes': 'Initial stock entry when item was created',
                    'createdAt': datetime.utcnow()
                }
                mongo.db.inventory_movements.insert_one(movement_data)
            
            # Return created item
            created_item = mongo.db.inventory_items.find_one({'_id': result.inserted_id})
            item_response = serialize_doc(created_item.copy())
            
            # Format dates
            item_response['createdAt'] = item_response.get('createdAt', datetime.utcnow()).isoformat() + 'Z'
            item_response['updatedAt'] = item_response.get('updatedAt', datetime.utcnow()).isoformat() + 'Z'
            item_response['lastRestocked'] = item_response.get('lastRestocked').isoformat() + 'Z' if item_response.get('lastRestocked') else None
            
            return jsonify({
                'success': True,
                'data': item_response,
                'message': 'Item added successfully'
            }), 201
            
        except Exception as e:
            return jsonify({
                'success': False,
                'message': 'Failed to add item',
                'errors': {'general': [str(e)]}
            }), 500

    @inventory_bp.route('/items', methods=['GET'])
    @token_required
    def get_items(current_user):
        """Get all inventory items with pagination and filtering"""
        try:
            page = int(request.args.get('page', 1))
            limit = int(request.args.get('limit', 10))
            category = request.args.get('category')
            status = request.args.get('status')
            search = request.args.get('search')
            low_stock_only = request.args.get('lowStockOnly', '').lower() == 'true'
            
            # Build query
            query = {'userId': current_user['_id']}
            
            if category:
                query['category'] = category
            
            if status:
                query['status'] = status
            
            if low_stock_only:
                query['$expr'] = {'$lte': ['$currentStock', '$minimumStock']}
            
            if search:
                query['$or'] = [
                    {'itemName': {'$regex': search, '$options': 'i'}},
                    {'itemCode': {'$regex': search, '$options': 'i'}},
                    {'description': {'$regex': search, '$options': 'i'}},
                    {'supplier': {'$regex': search, '$options': 'i'}}
                ]
            
            # Get items with pagination
            skip = (page - 1) * limit
            items = list(mongo.db.inventory_items.find(query).sort('itemName', 1).skip(skip).limit(limit))
            total = mongo.db.inventory_items.count_documents(query)
            
            # Serialize items
            item_list = []
            for item in items:
                item_data = serialize_doc(item.copy())
                item_data['createdAt'] = item_data.get('createdAt', datetime.utcnow()).isoformat() + 'Z'
                item_data['updatedAt'] = item_data.get('updatedAt', datetime.utcnow()).isoformat() + 'Z'
                item_data['lastRestocked'] = item_data.get('lastRestocked').isoformat() + 'Z' if item_data.get('lastRestocked') else None
                
                # Calculate profit margin
                if item['sellingPrice'] > 0:
                    profit_margin = ((item['sellingPrice'] - item['costPrice']) / item['sellingPrice']) * 100
                    item_data['profitMargin'] = round(profit_margin, 2)
                else:
                    item_data['profitMargin'] = 0
                
                # Check if item is low stock
                item_data['isLowStock'] = item['currentStock'] <= item['minimumStock']
                
                item_list.append(item_data)
            
            return jsonify({
                'success': True,
                'data': item_list,
                'pagination': {
                    'page': page,
                    'limit': limit,
                    'total': total,
                    'pages': (total + limit - 1) // limit
                },
                'message': 'Items retrieved successfully'
            })
            
        except Exception as e:
            return jsonify({
                'success': False,
                'message': 'Failed to retrieve items',
                'errors': {'general': [str(e)]}
            }), 500

    @inventory_bp.route('/summary', methods=['GET'])
    @token_required
    def get_summary(current_user):
        """Get inventory summary statistics"""
        try:
            # Get all items
            items = list(mongo.db.inventory_items.find({'userId': current_user['_id']}))
            
            # Calculate summary statistics
            total_items = len(items)
            total_value = sum(item['currentStock'] * item['costPrice'] for item in items)
            low_stock_items = len([item for item in items if item['currentStock'] <= item['minimumStock']])
            out_of_stock_items = len([item for item in items if item['currentStock'] <= 0])
            
            # Count by status
            active_items = len([item for item in items if item.get('status') == 'active'])
            
            # Calculate total stock quantity
            total_stock = sum(item['currentStock'] for item in items)
            
            summary_data = {
                'totalItems': total_items,
                'activeItems': active_items,
                'lowStockItems': low_stock_items,
                'outOfStockItems': out_of_stock_items,
                'totalValue': total_value,
                'totalStock': total_stock
            }
            
            return jsonify({
                'success': True,
                'data': summary_data,
                'message': 'Summary retrieved successfully'
            })
            
        except Exception as e:
            return jsonify({
                'success': False,
                'message': 'Failed to retrieve summary',
                'errors': {'general': [str(e)]}
            }), 500

    return inventory_bp