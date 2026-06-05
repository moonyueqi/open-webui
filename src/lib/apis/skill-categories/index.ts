import { WEBUI_API_BASE_URL } from '$lib/constants';

export const createSkillCategory = async (
	token: string,
	name: string,
	description: string,
	accessGrants: object[]
) => {
	let error = null;

	const res = await fetch(`${WEBUI_API_BASE_URL}/skill-categories/create`, {
		method: 'POST',
		headers: {
			Accept: 'application/json',
			'Content-Type': 'application/json',
			authorization: `Bearer ${token}`
		},
		body: JSON.stringify({
			name: name,
			description: description,
			access_grants: accessGrants
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

export const getSkillCategories = async (
	token: string = '',
	page: number | null = null,
	viewOption: string = '',
	query: string = ''
) => {
	let error = null;

	const searchParams = new URLSearchParams();
	if (page) searchParams.append('page', page.toString());
	if (viewOption) searchParams.append('view_option', viewOption);
	if (query) searchParams.append('query', query);

	const res = await fetch(
		`${WEBUI_API_BASE_URL}/skill-categories/?${searchParams.toString()}`,
		{
			method: 'GET',
			headers: {
				Accept: 'application/json',
				'Content-Type': 'application/json',
				authorization: `Bearer ${token}`
			}
		}
	)
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

export const getSkillCategoryById = async (token: string, id: string) => {
	let error = null;

	const res = await fetch(`${WEBUI_API_BASE_URL}/skill-categories/${id}`, {
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

export const updateSkillCategoryById = async (
	token: string,
	id: string,
	name: string,
	description: string,
	accessGrants: object[] | null = null
) => {
	let error = null;

	const res = await fetch(`${WEBUI_API_BASE_URL}/skill-categories/${id}/update`, {
		method: 'POST',
		headers: {
			Accept: 'application/json',
			'Content-Type': 'application/json',
			authorization: `Bearer ${token}`
		},
		body: JSON.stringify({
			name: name,
			description: description,
			access_grants: accessGrants
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

export const updateSkillCategoryAccessGrants = async (
	token: string,
	id: string,
	accessGrants: object[]
) => {
	let error = null;

	const res = await fetch(`${WEBUI_API_BASE_URL}/skill-categories/${id}/access/update`, {
		method: 'POST',
		headers: {
			Accept: 'application/json',
			'Content-Type': 'application/json',
			authorization: `Bearer ${token}`
		},
		body: JSON.stringify({
			access_grants: accessGrants
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

export const getSkillsByCategoryId = async (
	token: string,
	id: string,
	page: number | null = null,
	query: string = '',
	viewOption: string = ''
) => {
	let error = null;

	const searchParams = new URLSearchParams();
	if (page) searchParams.append('page', page.toString());
	if (query) searchParams.append('query', query);
	if (viewOption) searchParams.append('view_option', viewOption);

	const res = await fetch(
		`${WEBUI_API_BASE_URL}/skill-categories/${id}/skills?${searchParams.toString()}`,
		{
			method: 'GET',
			headers: {
				Accept: 'application/json',
				'Content-Type': 'application/json',
				authorization: `Bearer ${token}`
			}
		}
	)
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

export const deleteSkillCategoryById = async (token: string, id: string) => {
	let error = null;

	const res = await fetch(`${WEBUI_API_BASE_URL}/skill-categories/${id}/delete`, {
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
