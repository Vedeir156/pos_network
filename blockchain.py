import threading
import time
import json
import hashlib

class Block:
    def __init__(self, index, previous_hash, transactions, validator_id, slot, timestamp=None, hash=None):
        self.index = index
        self.timestamp = timestamp if timestamp is not None else time.time()
        self.transactions = transactions
        self.previous_hash = previous_hash
        self.validator_id = validator_id
        self.slot = slot
        self.hash = hash if hash is not None else self.calculate_own_hash()
    
    def calculate_own_hash(self):
        block_string = json.dumps({
            "index": self.index, "timestamp": self.timestamp,
            "transactions": self.transactions,
            "previous_hash": self.previous_hash, "validator_id": self.validator_id,
            "slot": self.slot
        }, sort_keys=True).encode()
        return hashlib.sha256(block_string).hexdigest()
        
    def to_dict(self):
        return {
            'index': self.index, 'timestamp': self.timestamp,
            'transactions': self.transactions,
            'previous_hash': self.previous_hash, 'validator_id': self.validator_id, 'hash': self.hash,
            'slot': self.slot
        }

    @staticmethod
    def from_dict(data):
        return Block(
            index=data.get('index'), previous_hash=data.get('previous_hash'),
            transactions=data.get('transactions'), validator_id=data.get('validator_id'),
            slot=data.get('slot'),
            timestamp=data.get('timestamp'), hash=data.get('hash')
        )
        
class Blockchain:
    def __init__(self):
        self.chain = []
        self.pending_transactions = []
        self.committed_transactions = set()
        self.lock = threading.Lock()
        self.create_genesis_block()

    def create_genesis_block(self):
        genesis_block = Block(index=1, previous_hash='1', transactions=[], validator_id="genesis",
                                timestamp=1672531200.0, slot=0)
        genesis_block.hash = genesis_block.calculate_own_hash()
        self.chain.append(genesis_block)

    def get_latest_block(self):
        return self.chain[-1]
    
    def add_transaction(self, transaction_data):
        tx_hash = hashlib.sha256(transaction_data.encode()).hexdigest()
        if tx_hash not in self.committed_transactions:
            self.pending_transactions.append(transaction_data)

    def create_block_candidate(self, parent_block, validator_name, slot):
        transactions_to_process = list(self.pending_transactions)
        self.pending_transactions.clear()

        return Block(
            index=parent_block.index + 1,
            previous_hash=parent_block.hash,
            transactions=transactions_to_process,
            validator_id=validator_name,
            slot=slot
        )

    def get_block_by_hash(self, block_hash):
        for block in reversed(self.chain):
            if block.hash == block_hash:
                return block
        return None

    def get_children(self, parent_hash):
        return [block for block in self.chain if block.previous_hash == parent_hash]