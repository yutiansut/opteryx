# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

from hadro import HadroDB

from .base_kv_store import BaseKeyValueStore
from .kv_firestore import FireStoreKVStore


def KV_store_factory(store):  # pragma: no-cover
    """
    A factory method for getting KV Store instances
    """
    stores = {
        "hadro": HadroDB,
        "firestore": FireStoreKVStore,
    }

    return stores.get(store.lower(), HadroDB)
