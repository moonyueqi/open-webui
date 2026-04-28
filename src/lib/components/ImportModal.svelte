<script lang="ts">
	import { toast } from 'svelte-sonner';
	import { getContext, onMount } from 'svelte';
	const i18n = getContext('i18n');

	import Spinner from '$lib/components/common/Spinner.svelte';
	import Modal from '$lib/components/common/Modal.svelte';
	import XMark from '$lib/components/icons/XMark.svelte';
	import { extractFrontmatter } from '$lib/utils';

	export let show = false;

	export let onImport = (e) => {};
	export let onClose = () => {};

	export let loadUrlHandler: Function = () => {};
	export let successMessage: string = '';

	let loading = false;
	let url = '';

	const submitHandler = async () => {
		loading = true;

		if (!url) {
			toast.error($i18n.t('Please enter a valid URL'));
			loading = false;
			return;
		}

		const res = await loadUrlHandler(url).catch((err) => {
			toast.error(`${err}`);
			loading = false;
			return null;
		});

		if (res) {
			if (!successMessage) {
				successMessage = $i18n.t('Function imported successfully');
			}

			toast.success(successMessage);

			let func = res;
			func.id = func.id || func.name.replace(/\s+/g, '_').toLowerCase();

			const frontmatter = extractFrontmatter(res.content); // Ensure frontmatter is extracted

			if (frontmatter?.title) {
				func.name = frontmatter.title;
			}

			func.meta = {
				...(func.meta ?? {}),
				description: frontmatter?.description ?? func.name
			};

			onImport(func);
			show = false;
		}
	};
</script>

<Modal size="sm" bind:show>
	<div>
		<div class="flex justify-between items-center dark:text-gray-300 px-5 pt-4 pb-3">
			<div class="text-lg font-semibold">{$i18n.t('Import')}</div>
			<button
				class="p-1 rounded-lg hover:bg-gray-100 dark:hover:bg-gray-800 transition"
				aria-label={$i18n.t('Close')}
				on:click={() => {
					show = false;
				}}
			>
				<XMark className={'size-5'} />
			</button>
		</div>

		<div class="px-5 pb-5 dark:text-gray-200">
			<form
				class="flex flex-col w-full"
				on:submit|preventDefault={() => {
					submitHandler();
				}}
			>
				<div class="flex items-center w-full border border-gray-200 dark:border-gray-700 rounded-lg px-3 py-2 focus-within:border-gray-400 dark:focus-within:border-gray-500 transition">
					<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 20 20" fill="currentColor" class="size-4 text-gray-400 dark:text-gray-500 shrink-0 mr-2">
						<path d="M12.232 4.232a2.5 2.5 0 0 1 3.536 3.536l-1.225 1.224a.75.75 0 0 0 1.061 1.06l1.224-1.224a4 4 0 0 0-5.656-5.656l-3 3a4 4 0 0 0 .225 5.865.75.75 0 0 0 .977-1.138 2.5 2.5 0 0 1-.142-3.667l3-3Z" />
						<path d="M11.603 7.963a.75.75 0 0 0-.977 1.138 2.5 2.5 0 0 1 .142 3.667l-3 3a2.5 2.5 0 0 1-3.536-3.536l1.225-1.224a.75.75 0 0 0-1.061-1.06l-1.224 1.224a4 4 0 1 0 5.656 5.656l3-3a4 4 0 0 0-.225-5.865Z" />
					</svg>
					<input
						class="w-full text-sm bg-transparent disabled:text-gray-500 dark:disabled:text-gray-500 outline-none placeholder-gray-400 dark:placeholder-gray-500"
						type="url"
						bind:value={url}
						placeholder={$i18n.t('Enter the URL to import')}
						required
					/>
				</div>

				<div class="flex justify-end pt-4">
					<button
						class="px-4 py-1.5 text-sm font-medium bg-black hover:bg-gray-900 text-white dark:bg-white dark:text-black dark:hover:bg-gray-100 transition rounded-lg flex items-center {loading
							? ' cursor-not-allowed'
							: ''}"
						type="submit"
						disabled={loading}
					>
						{$i18n.t('Import')}

						{#if loading}
							<div class="ml-2 self-center">
								<Spinner />
							</div>
						{/if}
					</button>
				</div>
			</form>
		</div>
	</div>
</Modal>
