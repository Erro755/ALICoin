"""
alicoin.py — AliCoin blockchain engine

This is the original AliCoin.ipynb logic (MerkleTree, Transaction, Block,
Account, Miner, AliCoin) pulled out of the notebook and into an importable
module so a UI can sit on top of it. Field names, class names, and the core
algorithms (Merkle root, SHA-256 proof-of-work, resource-weighted mining)
are unchanged from the notebook — a saved chain behaves the same way it did
there.

Two deliberate changes from the notebook, both about making the engine
UI-friendly rather than notebook-friendly:

1. print() -> return values / exceptions. The notebook reported success and
   failure with print(). A UI can't easily capture stdout, so every action
   now returns the object it created (or raises AliCoinError with a message
   the UI can show in st.error()).

2. multiprocessing -> simulated race. The notebook spawned one OS process
   per miner and had them race in real wall-clock time. That model assumes
   a long-running script; it does not fit Streamlit's "rerun the whole
   script on every click" execution model, and multiprocessing.Process
   behaves differently across platforms. mine_block() keeps the exact same
   idea — a miner's `resources` (1–10) shrinks the same random delay
   formula the notebook used in its sleep() call — but compares the drawn
   delays directly instead of actually sleeping in parallel processes. The
   proof-of-work hashing itself is still real, not faked.
"""

import hashlib
import random
from datetime import datetime


class AliCoinError(Exception):
    """Raised when a requested action can't be completed."""


class MerkleTree:
    def __init__(self, files):
        self.data = files

    def calculate_hashes(self):
        all_hashes = []
        initial_hashes = []

        for file in self.data:
            sha = hashlib.sha256()
            sha.update(str(file).encode())
            initial_hashes.append(sha.hexdigest())

        def merkle_root(hashes):
            all_hashes.extend(hashes)
            if not hashes:
                raise AliCoinError("Missing required files")
            if len(hashes) % 2 != 0:
                hashes.append(hashes[-1])
            new_hashes = []
            for pair in [hashes[i:i + 2] for i in range(0, len(hashes), 2)]:
                sha = hashlib.sha256()
                sha.update((str(pair[0]) + str(pair[1])).encode())
                new_hashes.append(sha.hexdigest())
            if len(new_hashes) == 1:
                return new_hashes[0]
            return merkle_root(new_hashes)

        root = merkle_root(initial_hashes)
        all_hashes.append(root)
        return root


class Transaction:
    def __init__(self, sender, recipient, amount):
        self.sender = sender
        self.recipient = recipient
        self.amount = amount
        self.id = None
        self.timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    def __str__(self):
        return (f"Transaction from {self.sender} to {self.recipient} at "
                f"{self.timestamp} | amount {self.amount} @ | ID: {self.id}")


class Block:
    def __init__(self, transactions, previous_hash, merkle_root, difficulty, hash, timestamp, nonce):
        self.index = None
        self.timestamp = timestamp
        self.transactions = transactions
        self.previous_hash = previous_hash
        self.merkle_root = merkle_root
        self.nonce = nonce
        self.difficulty = difficulty
        self.hash = hash

    def __str__(self):
        return (f"Block {self.index} | Hash: {self.hash} | Merkle root: {self.merkle_root} | "
                f"Timestamp: {self.timestamp} | Transactions: {len(self.transactions)} | "
                f"Previous Hash: {self.previous_hash} | Nonce: {self.nonce}")


class Account:
    def __init__(self, balance):
        self.balance = balance
        self.transactions = []
        self.id = None
        self.private_key = None
        self.public_key = None

    def __str__(self):
        return f"Account id: {self.id} | Balance: {self.balance} @ | Number of transactions: {len(self.transactions)}"


class Miner(Account):
    def __init__(self, difficulty, balance=0):
        super().__init__(balance)
        self.difficulty = difficulty
        self.block = []
        self.resources = random.randint(1, 10)

    def __str__(self):
        return f"Miner id: {self.id} | Balance: {self.balance} @ | Resources: {self.resources}"


class AliCoin:
    def __init__(self):
        self.accounts = {}
        self.miners = {}
        self.transactions = []
        self.blockchain = []
        self.difficulty = 0xFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFF

    # ---- accounts ----------------------------------------------------

    def add_account(self, balance):
        account = Account(balance)
        account.id = len(self.accounts)
        self.accounts[account.id] = account
        return account

    def get_account(self, account_id):
        return self.accounts[account_id]

    def get_balance(self, account_id):
        return self.accounts[account_id].balance

    # ---- miners --------------------------------------------------------

    def add_miner(self):
        miner = Miner(self.difficulty)
        miner.id = len(self.miners)
        self.miners[miner.id] = miner
        return miner

    # ---- transactions ---------------------------------------------------

    def add_transaction(self, sender_id, recipient_id, amount):
        if sender_id == recipient_id:
            raise AliCoinError("Sender and recipient must be different accounts.")
        sender = self.get_account(sender_id)
        recipient = self.get_account(recipient_id)
        if amount <= 0:
            raise AliCoinError("Amount must be greater than zero.")
        if sender.balance < amount:
            raise AliCoinError(
                f"Account {sender_id} has {sender.balance} @, can't send {amount} @."
            )
        tx = Transaction(sender_id, recipient_id, amount)
        tx.id = len(self.transactions)
        sender.balance -= amount
        recipient.balance += amount
        self.transactions.append(tx)
        sender.transactions.append(tx)
        recipient.transactions.append(tx)
        return tx

    def get_transaction(self, transaction_id):
        return self.transactions[transaction_id]

    # ---- chain / mining ---------------------------------------------------

    def create_genesis_block(self):
        if self.blockchain or not self.transactions:
            return None
        genesis = Block(
            self.transactions,
            "0",
            MerkleTree(self.transactions).calculate_hashes(),
            self.difficulty,
            "0",
            datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            0,
        )
        genesis.index = 0
        self.blockchain.append(genesis)
        self.transactions = []
        return genesis

    def add_block(self, transactions, merkle_root, hash_, timestamp, nonce):
        previous_hash = self.blockchain[-1].hash
        block = Block(transactions, previous_hash, merkle_root, self.difficulty, hash_, timestamp, nonce)
        block.index = len(self.blockchain)
        self.blockchain.append(block)
        self.transactions = []
        return block

    def mine_block(self):
        """
        Run one mining round on the current pending transactions.

        Returns a dict describing what happened:
          {"genesis": True, "block": Block}                                  -> first block created, no race
          {"genesis": False, "block": Block, "winner_id": int,
           "race_times": {miner_id: float}, "reward": 10}                    -> normal mined block
        Raises AliCoinError if there's nothing to mine or no miners exist.
        """
        if not self.blockchain:
            genesis = self.create_genesis_block()
            if genesis:
                return {"genesis": True, "block": genesis}

        if not self.transactions:
            raise AliCoinError("No pending transactions to mine.")
        if not self.miners:
            raise AliCoinError("No miners registered yet — add one first.")

        previous_hash = self.blockchain[-1].hash
        merkle_root = MerkleTree(self.transactions).calculate_hashes()

        # Same formula the notebook used inside its sleep() call — lower
        # resources draws a larger number, i.e. a slower miner.
        race_times = {
            miner_id: random.uniform(0, 0.0001) * (22 - 2 * miner.resources)
            for miner_id, miner in self.miners.items()
        }
        winner_id = min(race_times, key=race_times.get)

        nonce = 0
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        while True:
            header = f"{previous_hash}{merkle_root}{timestamp}{self.difficulty}{nonce}"
            result = hashlib.sha256(header.encode()).hexdigest()
            if int(result, 16) < self.difficulty:
                break
            nonce += 1

        self.miners[winner_id].balance += 10
        block = self.add_block(self.transactions, merkle_root, result, timestamp, nonce)

        return {
            "genesis": False,
            "block": block,
            "winner_id": winner_id,
            "race_times": race_times,
            "reward": 10,
        }
