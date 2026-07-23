import { WEBUI_API_BASE_URL } from '$lib/constants';

export const getMemories = async (token: string) => {
	let error = null;

	const res = await fetch(`${WEBUI_API_BASE_URL}/memories/`, {
		method: 'GET',
		headers: {
			Accept: 'application/json',
			'Content-Type': 'application/json',
			authorization: `Bearer ${token}`
		}
	})
		.then(async (res) => {
			if (!res.ok) throw await res.json();
			return res.json();
		})
		.catch((err) => {
			error = err.detail;
			console.error(err);
			return null;
		});

	if (error) {
		throw error;
	}

	return res;
};

export const addNewMemory = async (
	token: string,
	content: string,
	type: 'user' | 'context' = 'context',
	path: string | null = null
) => {
	let error = null;

	const res = await fetch(`${WEBUI_API_BASE_URL}/memories/add`, {
		method: 'POST',
		headers: {
			Accept: 'application/json',
			'Content-Type': 'application/json',
			authorization: `Bearer ${token}`
		},
		body: JSON.stringify({
			content: content,
			type: type,
			path: path
		})
	})
		.then(async (res) => {
			if (!res.ok) throw await res.json();
			return res.json();
		})
		.catch((err) => {
			error = err.detail;
			console.error(err);
			return null;
		});

	if (error) {
		throw error;
	}

	return res;
};

export const updateMemoryById = async (
	token: string,
	id: string,
	content: string | null = null,
	type: 'user' | 'context' | null = null,
	path: string | null = null
) => {
	let error = null;

	const res = await fetch(`${WEBUI_API_BASE_URL}/memories/${id}/update`, {
		method: 'POST',
		headers: {
			Accept: 'application/json',
			'Content-Type': 'application/json',
			authorization: `Bearer ${token}`
		},
		body: JSON.stringify({
			content: content,
			type: type,
			path: path
		})
	})
		.then(async (res) => {
			if (!res.ok) throw await res.json();
			return res.json();
		})
		.catch((err) => {
			error = err.detail;
			console.error(err);
			return null;
		});

	if (error) {
		throw error;
	}

	return res;
};

export const searchMemories = async (
	token: string,
	{
		query = null,
		type = 'all',
		path = null,
		memory_id = null,
		limit = 20
	}: {
		query?: string | null;
		type?: 'user' | 'context' | 'all';
		path?: string | null;
		memory_id?: string | null;
		limit?: number;
	} = {}
) => {
	let error = null;

	const res = await fetch(`${WEBUI_API_BASE_URL}/memories/search`, {
		method: 'POST',
		headers: {
			Accept: 'application/json',
			'Content-Type': 'application/json',
			authorization: `Bearer ${token}`
		},
		body: JSON.stringify({ query, type, path, memory_id, limit })
	})
		.then(async (res) => {
			if (!res.ok) throw await res.json();
			return res.json();
		})
		.catch((err) => {
			error = err.detail;
			console.error(err);
			return null;
		});

	if (error) {
		throw error;
	}

	return res;
};

export const listMemoryPaths = async (
	token: string,
	{
		query = null,
		type = 'all',
		limit = 100
	}: { query?: string | null; type?: 'user' | 'context' | 'all'; limit?: number } = {}
) => {
	let error = null;

	const res = await fetch(`${WEBUI_API_BASE_URL}/memories/paths`, {
		method: 'POST',
		headers: {
			Accept: 'application/json',
			'Content-Type': 'application/json',
			authorization: `Bearer ${token}`
		},
		body: JSON.stringify({ query, type, limit })
	})
		.then(async (res) => {
			if (!res.ok) throw await res.json();
			return res.json();
		})
		.catch((err) => {
			error = err.detail;
			console.error(err);
			return null;
		});

	if (error) {
		throw error;
	}

	return res;
};

export const readMemoryPath = async (
	token: string,
	{
		path,
		type = 'all',
		include_children = true,
		limit = 50
	}: {
		path: string;
		type?: 'user' | 'context' | 'all';
		include_children?: boolean;
		limit?: number;
	}
) => {
	let error = null;

	const res = await fetch(`${WEBUI_API_BASE_URL}/memories/path`, {
		method: 'POST',
		headers: {
			Accept: 'application/json',
			'Content-Type': 'application/json',
			authorization: `Bearer ${token}`
		},
		body: JSON.stringify({ path, type, include_children, limit })
	})
		.then(async (res) => {
			if (!res.ok) throw await res.json();
			return res.json();
		})
		.catch((err) => {
			error = err.detail;
			console.error(err);
			return null;
		});

	if (error) {
		throw error;
	}

	return res;
};

export const updateMemories = async (
	token: string,
	operations: Array<{
		action: 'add' | 'replace' | 'remove' | 'move';
		id?: string;
		content?: string;
		type?: 'user' | 'context';
		path?: string | null;
	}>,
	source: 'tool' | 'background_review' | null = null
) => {
	let error = null;

	const res = await fetch(`${WEBUI_API_BASE_URL}/memories/update`, {
		method: 'POST',
		headers: {
			Accept: 'application/json',
			'Content-Type': 'application/json',
			authorization: `Bearer ${token}`
		},
		body: JSON.stringify({ operations, source })
	})
		.then(async (res) => {
			if (!res.ok) throw await res.json();
			return res.json();
		})
		.catch((err) => {
			error = err.detail;
			console.error(err);
			return null;
		});

	if (error) {
		throw error;
	}

	return res;
};

export const queryMemory = async (token: string, content: string) => {
	let error = null;

	const res = await fetch(`${WEBUI_API_BASE_URL}/memories/query`, {
		method: 'POST',
		headers: {
			Accept: 'application/json',
			'Content-Type': 'application/json',
			authorization: `Bearer ${token}`
		},
		body: JSON.stringify({
			content: content
		})
	})
		.then(async (res) => {
			if (!res.ok) throw await res.json();
			return res.json();
		})
		.catch((err) => {
			error = err.detail;
			console.error(err);
			return null;
		});

	if (error) {
		throw error;
	}

	return res;
};

export const deleteMemoryById = async (token: string, id: string) => {
	let error = null;

	const res = await fetch(`${WEBUI_API_BASE_URL}/memories/${id}`, {
		method: 'DELETE',
		headers: {
			Accept: 'application/json',
			'Content-Type': 'application/json',
			authorization: `Bearer ${token}`
		}
	})
		.then(async (res) => {
			if (!res.ok) throw await res.json();
			return res.json();
		})
		.then((json) => {
			return json;
		})
		.catch((err) => {
			error = err.detail;

			console.error(err);
			return null;
		});

	if (error) {
		throw error;
	}

	return res;
};

export const deleteMemoriesByUserId = async (token: string) => {
	let error = null;

	const res = await fetch(`${WEBUI_API_BASE_URL}/memories/delete/user`, {
		method: 'DELETE',
		headers: {
			Accept: 'application/json',
			'Content-Type': 'application/json',
			authorization: `Bearer ${token}`
		}
	})
		.then(async (res) => {
			if (!res.ok) throw await res.json();
			return res.json();
		})
		.then((json) => {
			return json;
		})
		.catch((err) => {
			error = err.detail;

			console.error(err);
			return null;
		});

	if (error) {
		throw error;
	}

	return res;
};
