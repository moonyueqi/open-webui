<script lang="ts">
	import { toast } from 'svelte-sonner';
	import { DropdownMenu } from 'bits-ui';
	import { getContext } from 'svelte';

	import fileSaver from 'file-saver';
	const { saveAs } = fileSaver;

	import { downloadChatAsPDF } from '$lib/apis/utils';
	import { copyToClipboard, createMessagesList, removeDetails, removeAllDetails } from '$lib/utils';

	import {
		showControls,
		showArtifacts,
		mobile,
		temporaryChatEnabled,
		theme,
		user,
		settings,
		folders,
		showEmbeds,
		artifactContents
	} from '$lib/stores';
	import { flyAndScale } from '$lib/utils/transitions';
	import { getChatById } from '$lib/apis/chats';

	import Dropdown from '$lib/components/common/Dropdown.svelte';
	import Tags from '$lib/components/chat/Tags.svelte';
	import Clipboard from '$lib/components/icons/Clipboard.svelte';
	import AdjustmentsHorizontal from '$lib/components/icons/AdjustmentsHorizontal.svelte';
	import Cube from '$lib/components/icons/Cube.svelte';
	import Folder from '$lib/components/icons/Folder.svelte';
	import Share from '$lib/components/icons/Share.svelte';
	import ArchiveBox from '$lib/components/icons/ArchiveBox.svelte';
	import Messages from '$lib/components/chat/Messages.svelte';
	import Download from '$lib/components/icons/Download.svelte';

	const i18n = getContext('i18n');

	export let shareEnabled: boolean = false;

	export let shareHandler: Function;
	export let moveChatHandler: Function;

	export let archiveChatHandler: Function;

	// export let tagHandler: Function;

	export let chat;
	export let onClose: Function = () => {};
	export let scrollToTop: (() => void) | null = null;


	const getCleanMessages = (chatObj) => {
		const history = chatObj.chat.history;
		const messages = createMessagesList(history, history.currentId);
		return messages
			.filter((m) => m.role === 'user' || m.role === 'assistant')
			.map((m) => {
				let content = m.content || '';
				content = removeDetails(content, ['reasoning', 'code_interpreter']);
				content = removeAllDetails(content);
				content = content.trim();
				return { role: m.role, content };
			})
			.filter((m) => m.content.length > 0);
	};

	const getRoleName = (role) => (role === 'user' ? '用户' : '智能预报员');

	const getChatAsText = async () => {
		const msgs = getCleanMessages(chat);
		return msgs
			.map((m) => `${getRoleName(m.role)}：\n${m.content}`)
			.join('\n\n');
	};

	const downloadTxt = async () => {
		const chatText = await getChatAsText();
		let blob = new Blob([chatText], { type: 'text/plain' });
		saveAs(blob, `chat-${chat.chat.title}.txt`);
	};

	const downloadWord = async () => {
		const { Document, Packer, Paragraph, TextRun } = await import('docx');
		const msgs = getCleanMessages(chat);
		const paragraphs = [];

		for (const m of msgs) {
			paragraphs.push(
				new Paragraph({
					children: [
						new TextRun({
							text: m.role === 'user' ? '用户：' : '智能预报员：',
							bold: true,
							size: 24
						})
					],
					spacing: { before: 240 }
				})
			);
			for (const line of m.content.split('\n')) {
				paragraphs.push(
					new Paragraph({
						children: [new TextRun({ text: line, size: 22 })],
						spacing: { before: 60 }
					})
				);
			}
		}

		const doc = new Document({
			sections: [{ children: paragraphs }]
		});

		const blob = await Packer.toBlob(doc);
		saveAs(blob, `chat-${chat.chat.title}.docx`);
	};

	const downloadPdf = async () => {
		const { default: jsPDF } = await import('jspdf');
		const chatText = await getChatAsText();
		const doc = new jsPDF();

		const left = 15;
		const top = 20;
		const right = 15;
		const bottom = 20;
		const pageWidth = doc.internal.pageSize.getWidth();
		const pageHeight = doc.internal.pageSize.getHeight();
		const usableWidth = pageWidth - left - right;
		const fontSize = 10;
		doc.setFontSize(fontSize);
		const lineHeight = fontSize * 0.5;
		const paragraphs = chatText.split('\n');
		let y = top;

		for (let paragraph of paragraphs) {
			const lines = doc.splitTextToSize(paragraph, usableWidth);
			for (let line of lines) {
				if (y + lineHeight > pageHeight - bottom) {
					doc.addPage();
					y = top;
				}
				doc.text(line, left, y);
				y += lineHeight;
			}
			y += lineHeight * 0.3;
		}

		doc.save(`chat-${chat.chat.title}.pdf`);
	};

	const downloadJSONExport = async () => {
		if (chat.id) {
			let chatObj = null;

			if ((chat?.id ?? '').startsWith('local') || $temporaryChatEnabled) {
				chatObj = chat;
			} else {
				chatObj = await getChatById(localStorage.token, chat.id);
			}

			if (!chatObj) return;

			const msgs = getCleanMessages(chatObj);
			const exportData = msgs.map((m) => ({ [getRoleName(m.role)]: m.content }));

			let blob = new Blob([JSON.stringify(exportData, null, 2)], {
				type: 'application/json'
			});
			saveAs(blob, `chat-${chatObj.chat.title}.json`);
		}
	};
</script>

<Dropdown
	on:change={(e) => {
		if (e.detail === false) {
			onClose();
		}
	}}
>
	<slot />

	<div slot="content">
		<DropdownMenu.Content
			class="select-none w-full max-w-[200px] rounded-2xl px-1 py-1  border border-gray-100  dark:border-gray-800 z-50 bg-white dark:bg-gray-850 dark:text-white shadow-lg transition"
			sideOffset={8}
			side="bottom"
			align="end"
			transition={flyAndScale}
		>
			<!-- <DropdownMenu.Item draggable="false"
				class="flex gap-2 items-center px-3 py-1.5 text-sm  cursor-pointer dark:hover:bg-gray-800 rounded-xl"
				on:click={async () => {
					await showSettings.set(!$showSettings);
				}}
			>
				<svg
					xmlns="http://www.w3.org/2000/svg"
					fill="none"
					viewBox="0 0 24 24"
					stroke-width="1.5"
					stroke="currentColor"
					class="size-4"
				>
					<path
						stroke-linecap="round"
						stroke-linejoin="round"
						d="M9.594 3.94c.09-.542.56-.94 1.11-.94h2.593c.55 0 1.02.398 1.11.94l.213 1.281c.063.374.313.686.645.87.074.04.147.083.22.127.325.196.72.257 1.075.124l1.217-.456a1.125 1.125 0 0 1 1.37.49l1.296 2.247a1.125 1.125 0 0 1-.26 1.431l-1.003.827c-.293.241-.438.613-.43.992a7.723 7.723 0 0 1 0 .255c-.008.378.137.75.43.991l1.004.827c.424.35.534.955.26 1.43l-1.298 2.247a1.125 1.125 0 0 1-1.369.491l-1.217-.456c-.355-.133-.75-.072-1.076.124a6.47 6.47 0 0 1-.22.128c-.331.183-.581.495-.644.869l-.213 1.281c-.09.543-.56.94-1.11.94h-2.594c-.55 0-1.019-.398-1.11-.94l-.213-1.281c-.062-.374-.312-.686-.644-.87a6.52 6.52 0 0 1-.22-.127c-.325-.196-.72-.257-1.076-.124l-1.217.456a1.125 1.125 0 0 1-1.369-.49l-1.297-2.247a1.125 1.125 0 0 1 .26-1.431l1.004-.827c.292-.24.437-.613.43-.991a6.932 6.932 0 0 1 0-.255c.007-.38-.138-.751-.43-.992l-1.004-.827a1.125 1.125 0 0 1-.26-1.43l1.297-2.247a1.125 1.125 0 0 1 1.37-.491l1.216.456c.356.133.751.072 1.076-.124.072-.044.146-.086.22-.128.332-.183.582-.495.644-.869l.214-1.28Z"
					/>
					<path
						stroke-linecap="round"
						stroke-linejoin="round"
						d="M15 12a3 3 0 1 1-6 0 3 3 0 0 1 6 0Z"
					/>
				</svg>
				<div class="flex items-center">{$i18n.t('Settings')}</div>
			</DropdownMenu.Item> -->

			{#if scrollToTop}
				<DropdownMenu.Item
					draggable="false"
					class="flex gap-2 items-center px-3 py-1.5 text-sm cursor-pointer hover:bg-gray-50 dark:hover:bg-gray-800 rounded-xl select-none w-full"
					id="chat-scroll-to-top-button"
					on:click={() => {
						scrollToTop();
					}}
				>
					<svg
						xmlns="http://www.w3.org/2000/svg"
						fill="none"
						viewBox="0 0 24 24"
						stroke-width="1.5"
						stroke="currentColor"
						class="size-4"
					>
						<path
							stroke-linecap="round"
							stroke-linejoin="round"
							d="M4.5 10.5 12 3m0 0 7.5 7.5M12 3v18"
						/>
					</svg>
					<div class="flex items-center">{$i18n.t('Scroll to Top')}</div>
				</DropdownMenu.Item>

				<hr class="border-gray-50/30 dark:border-gray-800/30 my-1" />
			{/if}

			{#if ($artifactContents ?? []).length > 0}
				<DropdownMenu.Item
					draggable="false"
					class="flex gap-2 items-center px-3 py-1.5 text-sm cursor-pointer hover:bg-gray-50 dark:hover:bg-gray-800 rounded-xl select-none w-full"
					id="chat-artifacts-button"
					on:click={async () => {
						await showControls.set(true);
						await showArtifacts.set(true);
						await showEmbeds.set(false);
					}}
				>
					<Cube className=" size-4" strokeWidth="1.5" />
					<div class="flex items-center">{$i18n.t('Artifacts')}</div>
				</DropdownMenu.Item>

				<hr class="border-gray-50/30 dark:border-gray-800/30 my-1" />
			{/if}

			{#if !$temporaryChatEnabled && ($user?.role === 'admin' || ($user.permissions?.chat?.share ?? true))}
				<DropdownMenu.Item
					draggable="false"
					class="flex gap-2 items-center px-3 py-1.5 text-sm cursor-pointer hover:bg-gray-50 dark:hover:bg-gray-800 rounded-xl select-none w-full"
					id="chat-share-button"
					on:click={() => {
						shareHandler();
					}}
				>
					<Share strokeWidth="1.5" />
					<div class="flex items-center">{$i18n.t('Share')}</div>
				</DropdownMenu.Item>
			{/if}

			<DropdownMenu.Sub>
				<DropdownMenu.SubTrigger
					draggable="false"
					class="flex gap-2 items-center px-3 py-1.5 text-sm cursor-pointer hover:bg-gray-50 dark:hover:bg-gray-800 rounded-xl select-none w-full"
				>
					<Download strokeWidth="1.5" />

					<div class="flex items-center">{$i18n.t('Download')}</div>
				</DropdownMenu.SubTrigger>
				<DropdownMenu.SubContent
					class="select-none min-w-[80px] rounded-2xl p-1 z-50 bg-white dark:bg-gray-850 dark:text-white border border-gray-100  dark:border-gray-800 shadow-lg"
					transition={flyAndScale}
					sideOffset={8}
				>
					<DropdownMenu.Item
						draggable="false"
						class="flex gap-2 items-center px-3 py-1.5 text-sm cursor-pointer hover:bg-gray-50 dark:hover:bg-gray-800 rounded-xl select-none w-full"
						on:click={() => {
							downloadWord();
						}}
					>
						<div class="flex items-center line-clamp-1">Word</div>
					</DropdownMenu.Item>

					<DropdownMenu.Item
						draggable="false"
						class="flex gap-2 items-center px-3 py-1.5 text-sm cursor-pointer hover:bg-gray-50 dark:hover:bg-gray-800 rounded-xl select-none w-full"
						on:click={() => {
							downloadJSONExport();
						}}
					>
						<div class="flex items-center line-clamp-1">Json</div>
					</DropdownMenu.Item>

					<DropdownMenu.Item
						draggable="false"
						class="flex gap-2 items-center px-3 py-1.5 text-sm cursor-pointer hover:bg-gray-50 dark:hover:bg-gray-800 rounded-xl select-none w-full"
						on:click={() => {
							downloadPdf();
						}}
					>
						<div class="flex items-center line-clamp-1">PDF</div>
					</DropdownMenu.Item>

					<DropdownMenu.Item
						draggable="false"
						class="flex gap-2 items-center px-3 py-1.5 text-sm cursor-pointer hover:bg-gray-50 dark:hover:bg-gray-800 rounded-xl select-none w-full"
						on:click={() => {
							downloadTxt();
						}}
					>
						<div class="flex items-center line-clamp-1">TXT</div>
					</DropdownMenu.Item>
				</DropdownMenu.SubContent>
			</DropdownMenu.Sub>

			<DropdownMenu.Item
				draggable="false"
				class="flex gap-2 items-center px-3 py-1.5 text-sm cursor-pointer hover:bg-gray-50 dark:hover:bg-gray-800 rounded-xl select-none w-full"
				id="chat-copy-button"
				on:click={async () => {
					const res = await copyToClipboard(await getChatAsText()).catch((e) => {
						console.error(e);
					});

					if (res) {
						toast.success($i18n.t('Copied to clipboard'));
					}
				}}
			>
				<Clipboard className=" size-4" strokeWidth="1.5" />
				<div class="flex items-center">{$i18n.t('Copy')}</div>
			</DropdownMenu.Item>

			{#if false && !$temporaryChatEnabled && chat?.id}
				<hr class="border-gray-50/30 dark:border-gray-800/30 my-1" />

				<!-- Folders 功能已禁用
				{#if $folders.length > 0}
					<DropdownMenu.Sub>
						<DropdownMenu.SubTrigger
							draggable="false"
							class="flex gap-2 items-center px-3 py-1.5 text-sm cursor-pointer hover:bg-gray-50 dark:hover:bg-gray-800 rounded-xl select-none w-full"
						>
							<Folder strokeWidth="1.5" />

							<div class="flex items-center">{$i18n.t('Move')}</div>
						</DropdownMenu.SubTrigger>
						<DropdownMenu.SubContent
							class="select-none w-full max-w-[200px] rounded-2xl p-1 z-50 bg-white dark:bg-gray-850 dark:text-white border border-gray-100  dark:border-gray-800 shadow-lg max-h-52 overflow-y-auto scrollbar-hidden"
							transition={flyAndScale}
							sideOffset={8}
						>
							{#each $folders.sort((a, b) => b.updated_at - a.updated_at) as folder}
								{#if folder?.id}
									<DropdownMenu.Item
										draggable="false"
										class="flex gap-2 items-center px-3 py-1.5 text-sm cursor-pointer hover:bg-gray-50 dark:hover:bg-gray-800 rounded-xl overflow-hidden"
										on:click={() => {
											moveChatHandler(chat.id, folder.id);
										}}
									>
										<div class="shrink-0">
											<Folder strokeWidth="1.5" />
										</div>

										<div class="truncate">{folder.name ?? 'Folder'}</div>
									</DropdownMenu.Item>
								{/if}
							{/each}
						</DropdownMenu.SubContent>
					</DropdownMenu.Sub>
				{/if}
			-->

			<!-- 归档功能已禁用
			<DropdownMenu.Item
				draggable="false"
				class="flex gap-2 items-center px-3 py-1.5 text-sm  cursor-pointer hover:bg-gray-50 dark:hover:bg-gray-800 rounded-xl"
				on:click={() => {
					archiveChatHandler();
				}}
			>
				<ArchiveBox className="size-4" strokeWidth="1.5" />
				<div class="flex items-center">{$i18n.t('Archive')}</div>
			</DropdownMenu.Item>
			-->

			<!-- 添加标签功能已禁用
			<hr class="border-gray-50/30 dark:border-gray-800/30 my-1" />

			<div class="flex p-1">
				<Tags chatId={chat.id} />
			</div>
			-->
			{/if}
		</DropdownMenu.Content>
	</div>
</Dropdown>
