const values = new Map();

const isAvailableAsync = async () => true;

const setItemAsync = async (key, value) => {
  values.set(key, value);
};

const getItemAsync = async (key) => values.get(key) ?? null;

const deleteItemAsync = async (key) => {
  values.delete(key);
};

module.exports = {
  isAvailableAsync,
  setItemAsync,
  getItemAsync,
  deleteItemAsync,
};
