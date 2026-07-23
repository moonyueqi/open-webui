<script lang="ts">
	import { getContext } from 'svelte';

	const i18n = getContext('i18n');
</script>

<div class="flex flex-col items-center justify-center flex-1 min-h-0 text-center py-16">
	<div class="text-gray-300 dark:text-gray-600 mb-4">
		<svg
			xmlns="http://www.w3.org/2000/svg"
			fill="none"
			viewBox="0 0 24 24"
			stroke-width="1.5"
			stroke="currentColor"
			class="size-12 mx-auto"
		>
			<path
				stroke-linecap="round"
				stroke-linejoin="round"
				d="M2.25 15a4.5 4.5 0 0 0 4.5 4.5H18a3.75 3.75 0 0 0 1.332-7.257 3 3 0 0 0-3.758-3.848 5.25 5.25 0 0 0-10.233 2.33A4.502 4.502 0 0 0 2.25 15Z"
			/>
		</svg>
	</div>
	<div class="text-base font-medium text-gray-500 dark:text-gray-400">
		{$i18n.t('Upper-air Monitoring')}
	</div>
	<div class="text-sm text-gray-400 dark:text-gray-500 mt-1">
		{$i18n.t('No data available yet')}
	</div>
</div>
