<script lang="ts">
	import { toast } from 'svelte-sonner';
	import { getContext, onMount, onDestroy } from 'svelte';

	const i18n = getContext('i18n');

	import { user as _user } from '$lib/stores';
	import { getUserInfoById, searchUsers } from '$lib/apis/users';
	import { WEBUI_API_BASE_URL } from '$lib/constants';

	import XMark from '$lib/components/icons/XMark.svelte';
	import Pagination from '$lib/components/common/Pagination.svelte';
	import ProfilePreview from '$lib/components/channel/Messages/Message/ProfilePreview.svelte';
	import Tooltip from '$lib/components/common/Tooltip.svelte';
	import ChevronUp from '$lib/components/icons/ChevronUp.svelte';
	import ChevronDown from '$lib/components/icons/ChevronDown.svelte';
	import Spinner from '$lib/components/common/Spinner.svelte';
	import Checkbox from '$lib/components/common/Checkbox.svelte';
	import { getGroups } from '$lib/apis/groups';

	export let includeGroups = true;
	export let includeUsers = true;
	export let pagination = false;

	export let groupIds = [];
	export let userIds = [];

	let groups = null;
	let filteredGroups = [];

	$: filteredGroups = groups
		? groups.filter((group) => group.name.toLowerCase().includes(query.toLowerCase()))
		: [];

	let selectedGroup = {};
	let selectedUsers = {};

	let page = 1;
	let users = null;
	let total = null;

	let query = '';
	let searchDebounceTimer: ReturnType<typeof setTimeout>;
	let orderBy = 'name'; // default sort key
	let direction = 'asc'; // default sort order

	const getUserList = async () => {
		try {
			const res = await searchUsers(localStorage.token, query, orderBy, direction, page).catch(
				(error) => {
					toast.error(`${error}`);
					return null;
				}
			);

			if (res) {
				users = res.users;
				total = res.total;
			}
		} catch (err) {
			console.error(err);
		}
	};

	$: if (query !== undefined) {
		clearTimeout(searchDebounceTimer);
		searchDebounceTimer = setTimeout(() => {
			getUserList();
		}, 300);
	}

	onDestroy(() => {
		clearTimeout(searchDebounceTimer);
	});

	$: if (page !== null && orderBy !== null && direction !== null) {
		getUserList();
	}

	onMount(async () => {
		groups = await getGroups(localStorage.token, true).catch((error) => {
			console.error(error);
			return [];
		});

		if (userIds.length > 0) {
			userIds.forEach(async (id) => {
				const res = await getUserInfoById(localStorage.token, id).catch((error) => {
					console.error(error);
					return null;
				});
				if (res) {
					selectedUsers[id] = res;
				}
			});
		}
	});
</script>

<div class="">
	{#if users === null || total === null}
		<div class="flex items-center justify-center py-12">
			<Spinner className="size-5" />
		</div>
	{:else}
		{#if groupIds.length > 0 || userIds.length > 0}
			<div class="mb-3">
				<div class="text-xs text-gray-400 dark:text-gray-500 font-medium mb-1.5">
					{groupIds.length + userIds.length}
					{$i18n.t('selected')}
				</div>
				<div class="flex gap-1.5 flex-wrap">
					{#each groupIds as id}
						{#if selectedGroup[id]}
							<button
								type="button"
								class="inline-flex items-center gap-1.5 pl-2.5 pr-1.5 py-1 bg-blue-50 dark:bg-blue-900/30 text-blue-700 dark:text-blue-300 border border-blue-200 dark:border-blue-800 rounded-full text-xs font-medium hover:bg-blue-100 dark:hover:bg-blue-900/50 transition"
								on:click={() => {
									groupIds = groupIds.filter((gid) => gid !== id);
									delete selectedGroup[id];
								}}
							>
								{selectedGroup[id].name}
								<XMark className="size-3 opacity-60" />
							</button>
						{/if}
					{/each}
					{#each userIds as id}
						{#if selectedUsers[id]}
							<button
								type="button"
								class="inline-flex items-center gap-1.5 pl-2.5 pr-1.5 py-1 bg-blue-50 dark:bg-blue-900/30 text-blue-700 dark:text-blue-300 border border-blue-200 dark:border-blue-800 rounded-full text-xs font-medium hover:bg-blue-100 dark:hover:bg-blue-900/50 transition"
								on:click={() => {
									userIds = userIds.filter((uid) => uid !== id);
									delete selectedUsers[id];
								}}
							>
								{selectedUsers[id].name}
								<XMark className="size-3 opacity-60" />
							</button>
						{/if}
					{/each}
				</div>
			</div>
		{/if}

		<div class="relative mb-3">
			<div class="absolute inset-y-0 left-0 flex items-center pl-3 pointer-events-none text-gray-400">
				<svg
					xmlns="http://www.w3.org/2000/svg"
					viewBox="0 0 20 20"
					fill="currentColor"
					class="w-4 h-4"
				>
					<path
						fill-rule="evenodd"
						d="M9 3.5a5.5 5.5 0 100 11 5.5 5.5 0 000-11zM2 9a7 7 0 1112.452 4.391l3.328 3.329a.75.75 0 11-1.06 1.06l-3.329-3.328A7 7 0 012 9z"
						clip-rule="evenodd"
					/>
				</svg>
			</div>
			<input
				class="w-full text-sm py-2 pl-9 pr-4 rounded-xl outline-hidden bg-gray-50 dark:bg-gray-800/50 border border-gray-200 dark:border-gray-700 focus:border-gray-400 dark:focus:border-gray-500 transition placeholder:text-gray-400"
				bind:value={query}
				placeholder={$i18n.t('Search')}
			/>
		</div>

		{#if users.length > 0 || filteredGroups.length > 0}
			<div class="w-full max-h-72 overflow-y-auto scrollbar-thin rounded-xl border border-gray-100 dark:border-gray-800">
				{#if includeGroups && filteredGroups.length > 0}
					<div class="text-[11px] uppercase tracking-wider text-gray-400 dark:text-gray-500 font-semibold px-3 pt-2.5 pb-1">
						{$i18n.t('Groups')}
					</div>

					{#each filteredGroups as group, groupIdx (group.id)}
						<button
							class="flex items-center justify-between w-full px-3 py-2 hover:bg-gray-50 dark:hover:bg-gray-800/50 transition {(groupIds ?? []).includes(group.id) ? 'bg-blue-50/50 dark:bg-blue-900/10' : ''}"
							type="button"
							on:click={() => {
								if ((groupIds ?? []).includes(group.id)) {
									groupIds = groupIds.filter((id) => id !== group.id);
									delete selectedGroup[group.id];
								} else {
									groupIds = [...groupIds, group.id];
									selectedGroup[group.id] = group;
								}
							}}
						>
							<div class="flex items-center gap-2.5 flex-1 min-w-0">
								<div class="size-7 rounded-lg bg-gray-100 dark:bg-gray-800 flex items-center justify-center text-xs font-semibold text-gray-600 dark:text-gray-300 shrink-0">
									{group.name.charAt(0).toUpperCase()}
								</div>
								<div class="text-left min-w-0">
									<Tooltip content={group.name} placement="top-start">
										<div class="text-sm font-medium text-gray-900 dark:text-white truncate">
											{group.name}
										</div>
									</Tooltip>
									<div class="text-[11px] text-gray-400">
										{group.member_count} {$i18n.t('members')}
									</div>
								</div>
							</div>

							<div class="shrink-0 ml-2">
								<Checkbox
									state={(groupIds ?? []).includes(group.id) ? 'checked' : 'unchecked'}
								/>
							</div>
						</button>
					{/each}

					{#if includeUsers && users.length > 0}
						<div class="border-t border-gray-100 dark:border-gray-800 mx-3"></div>
					{/if}
				{/if}

				{#if includeUsers}
					<div class="text-[11px] uppercase tracking-wider text-gray-400 dark:text-gray-500 font-semibold px-3 pt-2.5 pb-1">
						{$i18n.t('Users')}
					</div>

					{#each users as user, userIdx (user.id)}
						{#if user?.id !== $_user?.id}
							<button
								class="flex items-center justify-between w-full px-3 py-2 hover:bg-gray-50 dark:hover:bg-gray-800/50 transition {(userIds ?? []).includes(user.id) ? 'bg-blue-50/50 dark:bg-blue-900/10' : ''}"
								type="button"
								on:click={() => {
									if ((userIds ?? []).includes(user.id)) {
										userIds = userIds.filter((id) => id !== user.id);
										delete selectedUsers[user.id];
									} else {
										userIds = [...userIds, user.id];
										selectedUsers[user.id] = user;
									}
								}}
							>
								<div class="flex items-center gap-2.5 flex-1 min-w-0">
									<ProfilePreview {user} side="right" align="center" sideOffset={6}>
										<img
											class="rounded-full size-7 object-cover shrink-0"
											src={`${WEBUI_API_BASE_URL}/users/${user.id}/profile/image`}
											alt="user"
										/>
									</ProfilePreview>
									<div class="text-left min-w-0">
										<Tooltip content={user.email} placement="top-start">
											<div class="text-sm font-medium text-gray-900 dark:text-white truncate flex items-center gap-1.5">
												{user.name}
												{#if user?.is_active}
													<span class="relative flex size-1.5">
														<span
															class="absolute inline-flex h-full w-full animate-ping rounded-full bg-green-400 opacity-75"
														></span>
														<span
															class="relative inline-flex size-1.5 rounded-full bg-green-500"
														></span>
													</span>
												{/if}
											</div>
										</Tooltip>
										{#if user.email}
											<div class="text-[11px] text-gray-400 truncate">{user.email}</div>
										{/if}
									</div>
								</div>

								<div class="shrink-0 ml-2">
									<Checkbox
										state={(userIds ?? []).includes(user.id) ? 'checked' : 'unchecked'}
									/>
								</div>
							</button>
						{/if}
					{/each}
				{/if}
			</div>
		{:else}
			<div class="flex flex-col items-center justify-center py-8 text-gray-400 dark:text-gray-500">
				<svg xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24" stroke-width="1.5" stroke="currentColor" class="w-8 h-8 mb-2 opacity-50">
					<path stroke-linecap="round" stroke-linejoin="round" d="M15.75 6a3.75 3.75 0 1 1-7.5 0 3.75 3.75 0 0 1 7.5 0ZM4.501 20.118a7.5 7.5 0 0 1 14.998 0A17.933 17.933 0 0 1 12 21.75c-2.676 0-5.216-.584-7.499-1.632Z" />
				</svg>
				<div class="text-xs">
					{$i18n.t('No users were found.')}
				</div>
			</div>
		{/if}
	{/if}
</div>
