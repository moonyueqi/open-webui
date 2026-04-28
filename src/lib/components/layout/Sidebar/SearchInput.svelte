<script lang="ts">
	import { getContext, createEventDispatcher } from 'svelte';
	import Search from '$lib/components/icons/Search.svelte';
	import XMark from '$lib/components/icons/XMark.svelte';

	const dispatch = createEventDispatcher();
	const i18n = getContext('i18n');

	export let placeholder = '';
	export let value = '';
	export let showClearButton = false;

	export let onFocus = () => {};
	export let onKeydown = (e) => {};

	/* 搜索选项功能已禁用 - 仅按标题搜索
	let selectedIdx = 0;
	let selectedOption = null;

	let lastWord = '';
	$: lastWord = value ? value.split(' ').at(-1) : value;

	let options = [
		{
			name: 'tag:',
			description: $i18n.t('search for tags')
		},
		{
			name: 'folder:',
			description: $i18n.t('search for folders')
		},
		{
			name: 'pinned:',
			description: $i18n.t('search for pinned chats')
		},
		{
			name: 'shared:',
			description: $i18n.t('search for shared chats')
		},
		{
			name: 'archived:',
			description: $i18n.t('search for archived chats')
		}
	];
	let focused = false;
	let loading = false;

	let hovering = false;

	let filteredOptions = options;
	$: filteredOptions = options.filter((option) => {
		return option.name.startsWith(lastWord);
	});

	let filteredItems = [];

	$: if (lastWord && lastWord !== null) {
		initItems();
	}

	const initItems = async () => {
		console.log('initItems', lastWord);
		loading = true;
		await tick();

		if (lastWord.startsWith('tag:')) {
			filteredItems = [
				...$tags,
				{
					id: 'none',
					name: $i18n.t('Untagged')
				}
			]
				.filter((tag) => {
					const tagName = lastWord.slice(4);
					if (tagName) {
						const tagId = tagName.replaceAll(' ', '_').toLowerCase();

						if (tag.id !== tagId) {
							return tag.id.startsWith(tagId);
						} else {
							return false;
						}
					} else {
						return true;
					}
				})
				.map((tag) => {
					return {
						id: tag.id,
						name: tag.name,
						type: 'tag'
					};
				});
		} else if (lastWord.startsWith('folder:')) {
			filteredItems = [...$folders]
				.filter((folder) => {
					const folderName = lastWord.slice(7);
					if (folderName) {
						const id = folder.name.replaceAll(' ', '_').toLowerCase();
						const folderId = folderName.replaceAll(' ', '_').toLowerCase();

						if (id !== folderId) {
							return id.startsWith(folderId);
						} else {
							return false;
						}
					} else {
						return true;
					}
				})
				.map((folder) => {
					return {
						id: folder.name.replaceAll(' ', '_').toLowerCase(),
						name: folder.name,
						type: 'folder'
					};
				});
		} else if (lastWord.startsWith('pinned:')) {
			filteredItems = [
				{
					id: 'true',
					name: 'true',
					type: 'pinned'
				},
				{
					id: 'false',
					name: 'false',
					type: 'pinned'
				}
			].filter((item) => {
				const pinnedValue = lastWord.slice(7);
				if (pinnedValue) {
					return item.id.startsWith(pinnedValue) && item.id !== pinnedValue;
				} else {
					return true;
				}
			});
		} else if (lastWord.startsWith('shared:')) {
			filteredItems = [
				{
					id: 'true',
					name: 'true',
					type: 'shared'
				},
				{
					id: 'false',
					name: 'false',
					type: 'shared'
				}
			].filter((item) => {
				const sharedValue = lastWord.slice(7);
				if (sharedValue) {
					return item.id.startsWith(sharedValue) && item.id !== sharedValue;
				} else {
					return true;
				}
			});
		} else if (lastWord.startsWith('archived:')) {
			filteredItems = [
				{
					id: 'true',
					name: 'true',
					type: 'archived'
				},
				{
					id: 'false',
					name: 'false',
					type: 'archived'
				}
			].filter((item) => {
				const archivedValue = lastWord.slice(9);
				if (archivedValue) {
					return item.id.startsWith(archivedValue) && item.id !== archivedValue;
				} else {
					return true;
				}
			});
		} else {
			filteredItems = [];
		}

		loading = false;
	};

	const initTags = async () => {
		loading = true;

		await tags.set(await getAllTags(localStorage.token));
		loading = false;
	};
	搜索选项功能已禁用 */

	let focused = false;

	const clearSearchInput = () => {
		value = '';
		dispatch('input');
	};
</script>

<div class="px-1 mb-1 flex justify-center space-x-2 relative z-10" id="search-container">
	<div class="flex w-full rounded-lg bg-gray-100 dark:bg-gray-800 border border-gray-200 dark:border-gray-700" id="chat-search">
		<div class="self-center pl-2.5 py-2 bg-transparent text-gray-400 dark:text-gray-400">
			<Search />
		</div>

		<input
			id="search-input"
			class="w-full rounded-r-lg py-1.5 pl-2.5 pr-2 text-sm bg-transparent dark:text-gray-300 outline-hidden placeholder-gray-400 dark:placeholder-gray-500"
			placeholder={placeholder ? placeholder : $i18n.t('Search')}
			autocomplete="off"
			maxlength="500"
			bind:value
			on:input={() => {
				dispatch('input');
			}}
			on:click={() => {
				if (!focused) {
					onFocus();
					focused = true;
				}
			}}
			on:blur={() => {
				focused = false;
			}}
			on:keydown={(e) => {
				onKeydown(e);
			}}
		/>

		{#if showClearButton && value}
			<div class="self-center pr-2 translate-y-[0.5px] bg-transparent">
				<button
					class="p-0.5 rounded-full hover:bg-gray-200 dark:hover:bg-gray-700 transition"
					on:click={clearSearchInput}
				>
					<XMark className="size-3" strokeWidth="2" />
				</button>
			</div>
		{/if}
	</div>
</div>
